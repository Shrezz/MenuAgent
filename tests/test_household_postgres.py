"""Integration tests create and remove their own database, never the app's data."""
from dataclasses import replace
from hashlib import sha256
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from streamlit import config as st_config
from streamlit.testing.v1 import AppTest

from application.domain.models import Member
from application.repositories.households import HouseholdRepository
from application.services.households import HouseholdService
from application.services.recipe_examples import example_recipe
from application.repositories.recipes import RecipeRepository
from application.domain.nutrition import calculate_recipe
from database.connection import AccessDenied, ConcurrentChange, Database, EditorContext, StorageUnavailable
from database.manage import bootstrap_household, grant_app_role, migrate
from application.repositories.receipts import ReceiptRepository
from application.domain.receipts import receipt_hash, extraction_rows
from test_receipts import receipt_image, receipt_result
from io import BytesIO

ENABLED = bool(os.environ.get('MENUAGENT_TEST_ADMIN_DATABASE_URL') and os.environ.get('MENUAGENT_TEST_DATABASE_URL'))
APP_PATH = Path(__file__).resolve().parents[1] / 'streamlit_app.py'


@unittest.skipUnless(ENABLED, 'Set both MenuAgent test database URLs to run real PostgreSQL integration tests.')
class HouseholdPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_name = 'menuagent_test_' + uuid4().hex
        cls.admin_base = make_conninfo(os.environ['MENUAGENT_TEST_ADMIN_DATABASE_URL'], dbname='postgres')
        with psycopg.connect(cls.admin_base, autocommit=True) as conn:
            conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(cls.database_name)))
        cls.addClassCleanup(cls.drop_database)
        cls.admin = make_conninfo(cls.admin_base, dbname=cls.database_name)
        cls.app_conninfo = make_conninfo(os.environ['MENUAGENT_TEST_DATABASE_URL'], dbname=cls.database_name)
        migrate(cls.admin)
        with psycopg.connect(cls.app_conninfo) as conn:
            role = conn.execute('SELECT current_user').fetchone()[0]
        grant_app_role(cls.admin, role)
        cls.old_address = st_config.get_option('server.address')
        st_config.set_option('server.address', '127.0.0.1')
        cls.addClassCleanup(st_config.set_option, 'server.address', cls.old_address)

    @classmethod
    def drop_database(cls):
        with psycopg.connect(cls.admin_base, autocommit=True) as conn:
            conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(cls.database_name)))

    def setUp(self):
        self.a, self.b = str(uuid4()), str(uuid4())
        bootstrap_household(self.admin, self.a, 'Household A', 'alice')
        bootstrap_household(self.admin, self.b, 'Household B', 'bob')
        self.context = EditorContext(self.a, 'alice')
        self.repo = HouseholdRepository(Database(self.app_conninfo), self.context)
        self.other = HouseholdRepository(Database(self.app_conninfo), EditorContext(self.b, 'bob'))

    def test_migration_rerun_is_safe(self):
        migrate(self.admin)
        with psycopg.connect(self.admin) as conn:
            count = conn.execute('SELECT count(*) FROM menuagent.schema_migrations').fetchone()[0]
        self.assertEqual(count, 4)

    def test_receipt_confirmation_is_durable_atomic_and_once_only(self):
        service = HouseholdService(self.repo)
        image, result = receipt_image(), receipt_result()
        receipts = ReceiptRepository(self.repo)
        record = receipts.save_extraction(image, result)
        self.assertEqual(self.repo.read().inventory, [])
        self.assertEqual(self.repo.read().version, 1)
        # Re-reading after a session reset reuses the stored extraction.
        with patch('integrations.ollama.OllamaReceiptReader.extract') as read:
            self.assertEqual(service.receipt_review.read(image)['extraction'], result['extraction'])
            read.assert_not_called()
        rows = extraction_rows(record['extraction'])
        rows[0]['Quantity'] = 350
        service.receipt_review.confirm(record['image_hash'], rows)
        self.assertEqual(HouseholdService(self.repo).inventory[0]['Quantity'], 350)
        self.assertIsNone(self.repo.read().inventory[1]['Quantity'])
        self.assertEqual(receipts.find(record['image_hash'])['reviewed_items'][0]['Quantity'], 350)
        with self.assertRaises(ValueError):
            HouseholdService(self.repo).receipt_review.confirm(record['image_hash'], rows)
        self.assertEqual(self.repo.read().version, 2)
        self.assertEqual(self.repo.read().inventory[0]['Quantity'], 350)

    def test_stale_receipt_confirmation_can_be_retried_after_reload(self):
        service = HouseholdService(self.repo)
        receipts = ReceiptRepository(self.repo)
        record = receipts.save_extraction(receipt_image(), receipt_result())
        self.repo.save_inventory([{'Item': 'Yogurt', 'Location': 'Fridge', 'Quantity': 500, 'Unit': 'g'}], 1)
        rows = extraction_rows(record['extraction'])
        with self.assertRaises(ConcurrentChange):
            service.receipt_review.confirm(record['image_hash'], rows)
        self.assertIsNone(receipts.find(record['image_hash'])['confirmed_at'])
        self.assertEqual(self.repo.read().inventory[0]['Quantity'], 500)
        service.refresh()
        service.receipt_review.confirm(record['image_hash'], rows)
        self.assertEqual(self.repo.read().inventory[0]['Quantity'], 1500)

    def test_receipt_image_provenance_is_immutable_and_household_scoped(self):
        receipts = ReceiptRepository(self.repo)
        image = receipt_image()
        record = receipts.save_extraction(image, receipt_result())
        changed = receipt_result()
        changed['extraction']['items'][0]['quantity'] = 999
        self.assertEqual(receipts.save_extraction(image, changed)['extraction']['items'][0]['quantity'], 1000)
        self.assertIsNone(ReceiptRepository(self.other).find(record['image_hash']))
        with Database(self.app_conninfo).transaction(EditorContext(self.b, 'bob')) as conn:
            self.assertEqual(conn.execute('SELECT count(*) AS n FROM menuagent.receipts').fetchone()['n'], 0)
        with self.assertRaises(AccessDenied):
            ReceiptRepository(HouseholdRepository(Database(self.app_conninfo), EditorContext(self.a, 'bob'))).find(record['image_hash'])
        with self.assertRaises(StorageUnavailable):
            with Database(self.app_conninfo).transaction(self.context) as conn:
                conn.execute("UPDATE menuagent.receipts SET model = 'forged'")
        with Database(self.app_conninfo).transaction(self.context) as conn:
            stored = conn.execute('SELECT image_bytes FROM menuagent.receipts').fetchone()['image_bytes']
        self.assertEqual(bytes(stored), image)

    def test_failed_receipt_transaction_preserves_receipt_stock_and_version(self):
        service = HouseholdService(self.repo)
        service.save_inventory([{'Item': 'Rice', 'Quantity': 1000}])
        receipt = ReceiptRepository(self.repo).save_extraction(receipt_image(), receipt_result())
        before = self.repo.read()
        with psycopg.connect(self.admin) as conn:
            conn.execute("""CREATE OR REPLACE FUNCTION menuagent.reject_test_inventory() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'Simulated database write failure'; END $$""")
            conn.execute("""CREATE TRIGGER reject_test_inventory BEFORE INSERT ON menuagent.inventory_items
                FOR EACH ROW WHEN (NEW.name = 'Rejected ingredient') EXECUTE FUNCTION menuagent.reject_test_inventory()""")
        self.addCleanup(self.remove_failure_trigger)
        with self.assertRaises(StorageUnavailable):
            service.receipt_review.confirm(receipt['image_hash'], [{'Item': 'Rejected ingredient', 'Quantity': 100}])
        self.assertEqual(self.repo.read().inventory, before.inventory)
        self.assertEqual(self.repo.read().version, before.version)
        self.assertIsNone(ReceiptRepository(self.repo).find(receipt['image_hash'])['confirmed_at'])

    def test_receipt_ui_review_and_new_session_preserve_duplicate_guard(self):
        with self.ui_environment(), patch('streamlit.file_uploader', return_value=BytesIO(receipt_image())), \
             patch('integrations.ollama.OllamaReceiptReader.extract', return_value=receipt_result()) as read:
            app = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
            app.switch_page('application/ui/pages/groceries.py').run()
            self.button(app, 'Read receipt with Ollama').click().run()
            self.assertEqual(self.repo.read().inventory, [])
            app.session_state['receipt-stock-' + receipt_hash(receipt_image())] = {
                'edited_rows': {0: {'Quantity': 300.0}}, 'deleted_rows': [], 'added_rows': []}
            self.button(app, 'Confirm reviewed purchases').click().run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            self.assertEqual(self.repo.read().inventory[0]['Quantity'], 300)
            reopened = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
            reopened.switch_page('application/ui/pages/groceries.py').run()
            self.assertFalse(reopened.exception)
            self.assertTrue(self.button(reopened, 'Read receipt with Ollama').disabled)
            self.assertTrue(any('already confirmed' in message.value for message in reopened.success))
            self.assertEqual(read.call_count, 1)

    def test_upgrade_preserves_records_without_guessing_effort_from_minutes(self):
        name = 'menuagent_upgrade_' + uuid4().hex
        with psycopg.connect(self.admin_base, autocommit=True) as conn:
            conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            admin = make_conninfo(self.admin_base, dbname=name)
            initial = APP_PATH.parent / 'database/migrations/001_household_records.sql'
            content = initial.read_bytes()
            with psycopg.connect(admin) as conn:
                conn.execute(content.decode(), prepare=False)
                conn.execute('CREATE TABLE menuagent.schema_migrations (name text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())')
                conn.execute('INSERT INTO menuagent.schema_migrations (name, checksum) VALUES (%s, %s)',
                             (initial.name, sha256(content).hexdigest()))
                conn.execute("INSERT INTO menuagent.households (id, name, cuisines, daily_minutes, batch_minutes) VALUES (%s, 'Existing household', ARRAY['Indian'], 45, 60)", (self.a,))
                conn.execute("INSERT INTO menuagent.members (household_id, id, name, kind) VALUES (%s, %s, 'Alex', 'Adult')", (self.a, str(uuid4())))
            migrate(admin)
            migrate(admin)
            with psycopg.connect(admin) as conn:
                row = conn.execute('SELECT cuisines, daily_minutes, batch_minutes, cooking_effort, meal_prep, busy_days FROM menuagent.households WHERE id = %s', (self.a,)).fetchone()
                self.assertEqual(row, (['Indian'], 45, 60, None, None, []))
                self.assertEqual(conn.execute('SELECT name FROM menuagent.members').fetchone()[0], 'Alex')
        finally:
            with psycopg.connect(self.admin_base, autocommit=True) as conn:
                conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))

    def test_profiles_preferences_and_stock_survive_a_new_service(self):
        service = HouseholdService(self.repo)
        service.add_member('Alex')
        adult = service.members[0]
        service.save_member(replace(adult, targets={'kcal': 2100, 'protein': 125, 'carbs': 240, 'fat': 65}, restrictions='Peanuts'))
        service.add_member('Sam', 'Child', 'School age')
        service.save_settings(['Indian', 'Mediterranean'], 'simple', 'small', ['Wednesday', 'Monday'])
        service.save_inventory([{'Item': 'Yogurt', 'Location': 'Fridge', 'Quantity': 500, 'Unit': 'g'}, {'Item': 'Olive oil', 'Quantity': None, 'Unit': 'ml'}])
        reopened = HouseholdService(HouseholdRepository(Database(self.app_conninfo), self.context))
        by_name = {member.name: member for member in reopened.members}
        self.assertEqual(by_name['Alex'].targets['protein'], 125)
        self.assertEqual(by_name['Alex'].restrictions, 'Peanuts')
        self.assertIsNone(by_name['Sam'].targets)
        self.assertEqual(reopened.cuisines, ['Indian', 'Mediterranean'])
        self.assertEqual((reopened.cooking_effort, reopened.meal_prep, reopened.busy_days), ('simple', 'small', ['Monday', 'Wednesday']))
        self.assertIsNone(reopened.inventory[1]['Quantity'])
        self.assertEqual(self.other.read().members, [])

    def test_forged_household_or_unknown_editor_cannot_read_or_write(self):
        for context in (EditorContext(self.b, 'alice'), EditorContext(self.a, 'outsider')):
            repository = HouseholdRepository(Database(self.app_conninfo), context)
            with self.assertRaises(AccessDenied):
                repository.read()
            with self.assertRaises(AccessDenied):
                repository.save_settings(['Indian'], 'simple', 'small', [], 1)
        self.assertEqual(self.other.read().version, 1)

    def test_raw_database_queries_are_scoped_by_rls(self):
        shared_id = str(uuid4())
        self.repo.save_member(Member(shared_id, 'Alex'), 1)
        self.other.save_member(Member(shared_id, 'Other Alex'), 1)
        with Database(self.app_conninfo).transaction(self.context) as conn:
            names = [row['name'] for row in conn.execute('SELECT name FROM menuagent.members').fetchall()]
            changed = conn.execute("UPDATE menuagent.members SET name = 'Wrong' WHERE household_id = %s", (self.b,))
            self.assertEqual(changed.rowcount, 0)
        self.assertEqual(names, ['Alex'])
        self.assertEqual(self.other.read().members[0].name, 'Other Alex')
        with psycopg.connect(self.app_conninfo) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM menuagent.members').fetchone()[0], 0)

    def test_app_cannot_grant_itself_editor_access(self):
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            with psycopg.connect(self.app_conninfo) as conn:
                conn.execute('INSERT INTO menuagent.editor_access VALUES (%s,%s)', (self.b, 'alice'))

    def test_application_rejects_admin_connections(self):
        with self.assertRaises(AccessDenied):
            HouseholdRepository(Database(self.admin), self.context).read()

    def test_stale_session_cannot_overwrite_newer_preferences(self):
        first, stale = HouseholdService(self.repo), HouseholdService(self.repo)
        first.save_settings(['Indian'], 'simple', 'small', [])
        with self.assertRaises(ConcurrentChange):
            stale.save_settings(['Mexican'], 'flexible', 'larger', ['Friday'])
        self.assertEqual(self.repo.read().cuisines, ['Indian'])
        stale.refresh()
        stale.save_settings(['Mexican'], 'simple', 'small', [])
        self.assertEqual(self.repo.read().cuisines, ['Mexican'])

    def test_failed_stock_transaction_rolls_back_deletion_and_version(self):
        service = HouseholdService(self.repo)
        service.save_inventory([{'Item': 'Rice', 'Quantity': 1000}])
        before = self.repo.read()
        with psycopg.connect(self.admin) as conn:
            conn.execute("""CREATE OR REPLACE FUNCTION menuagent.reject_test_inventory() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'Simulated database write failure'; END $$""")
            conn.execute("""CREATE TRIGGER reject_test_inventory BEFORE INSERT ON menuagent.inventory_items
                FOR EACH ROW WHEN (NEW.name = 'Rejected ingredient') EXECUTE FUNCTION menuagent.reject_test_inventory()""")
        self.addCleanup(self.remove_failure_trigger)
        with self.assertRaises(StorageUnavailable):
            service.save_inventory([{'Item': 'Peas', 'Quantity': 500}, {'Item': 'Rejected ingredient', 'Quantity': 100}])
        after = self.repo.read()
        self.assertEqual(after.inventory, before.inventory)
        self.assertEqual(after.version, before.version)

    def test_save_does_not_adopt_a_concurrent_unseen_version(self):
        service = HouseholdService(self.repo)
        original_save = self.repo.save_member

        def interleaved_save(member, expected_version):
            version = original_save(member, expected_version)
            # Another editor commits between this save and its UI response.
            self.repo.save_settings(['Mexican'], 'simple', 'small', [], version)
            return version

        with patch.object(self.repo, 'save_member', side_effect=interleaved_save):
            service.add_member('Alex')
        self.assertEqual(service.household_version, 2)
        with self.assertRaises(ConcurrentChange):
            service.save_settings(['Indian'], 'simple', 'small', [])
        self.assertEqual(self.repo.read().cuisines, ['Mexican'])

    def remove_failure_trigger(self):
        with psycopg.connect(self.admin) as conn:
            conn.execute('DROP TRIGGER IF EXISTS reject_test_inventory ON menuagent.inventory_items')

    def test_invalid_profile_does_not_replace_valid_values(self):
        service = HouseholdService(self.repo)
        service.add_member('Alex')
        original = service.members[0]
        version = service.household_version
        with self.assertRaises(ValueError):
            service.save_member(replace(original, targets={'kcal': 2000, 'protein': float('inf'), 'carbs': 250, 'fat': 65}))
        self.assertIsNone(self.repo.read().members[0].targets)
        self.assertEqual(self.repo.read().version, version)

    def test_sample_receipt_does_not_pollute_actual_inventory(self):
        service = HouseholdService(self.repo)
        with self.assertRaises(ValueError):
            service.confirm_sample_receipt(service.receipt_items)
        self.assertEqual(self.repo.read().inventory, [])

    def test_persistent_ui_sample_confirmation_uses_separate_stock(self):
        service = HouseholdService(self.repo)
        service.save_inventory([{'Item': 'Rice', 'Quantity': 1000}])
        before = self.repo.read()
        with self.ui_environment():
            app = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
            app.switch_page('application/ui/pages/groceries.py').run()
            self.button(app, 'Load sample receipt').click().run()
            self.assertFalse(self.button(app, 'Confirm sample purchases').disabled)
            app.session_state['receipt-editor'] = {'edited_rows': {0: {'Quantity': 350.0}},
                                                    'deleted_rows': [], 'added_rows': []}
            self.button(app, 'Confirm sample purchases').click().run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            self.assertTrue(self.button(app, 'Confirm sample purchases').disabled)
            preview = app.session_state['_receipt_sample_service']
            self.assertEqual(preview.inventory[0]['Quantity'], 350.0)
            self.assertEqual(len(preview.inventory), 4)
            self.assertEqual(self.repo.read().inventory, before.inventory)
            self.assertEqual(self.repo.read().version, before.version)
            self.button(app, 'Load sample receipt').click().run()
            self.assertTrue(self.button(app, 'Confirm sample purchases').disabled)
            self.assertEqual(len(preview.inventory), 4)


    def test_recipe_revisions_and_food_snapshots_survive_new_services(self):
        service = HouseholdService(self.repo)
        recipe = service.recipe_library.save(example_recipe())
        first = calculate_recipe(recipe)['totals']
        document = dict(recipe, name='Updated household bowl')
        document['ingredients'] = [dict(line, quantity=line['quantity'] * 2) for line in recipe['ingredients']]
        updated = service.recipe_library.save(document)
        source = dict(recipe['ingredients'][0]['food'])
        source['nutrients'] = dict(source['nutrients'], kcal=999)
        service.recipe_library.save_food(source)
        reopened = HouseholdService(self.repo)
        self.assertEqual(reopened.recipe_library.recipes[recipe['id']]['revision'], 2)
        revisions = reopened.recipe_library.revisions(recipe['id'])
        self.assertEqual(len(revisions), 2)
        self.assertEqual(calculate_recipe(revisions[0])['totals'], first)
        self.assertAlmostEqual(calculate_recipe(updated)['totals']['kcal'], first['kcal'] * 2)
        self.assertEqual(reopened.recipe_library.foods[source['id']]['nutrients']['kcal'], 999)
        self.assertEqual(HouseholdService(self.other).recipe_library.recipes, {})

    def test_recipe_writes_are_versioned_and_cross_household_scoped(self):
        first, stale = HouseholdService(self.repo), HouseholdService(self.repo)
        saved = first.recipe_library.save(example_recipe())
        with self.assertRaises(ConcurrentChange):
            stale.recipe_library.save(example_recipe())
        forged = RecipeRepository(HouseholdRepository(Database(self.app_conninfo), EditorContext(self.b, 'alice')))
        self.assertEqual(forged.read(), ({}, {}))
        with self.assertRaises(AccessDenied):
            forged.save(example_recipe(), 1)
        with Database(self.app_conninfo).transaction(EditorContext(self.b, 'bob')) as conn:
            self.assertEqual(conn.execute('SELECT count(*) AS n FROM menuagent.recipe_versions').fetchone()['n'], 0)
        self.assertEqual(first.recipe_library.recipes[saved['id']]['revision'], 1)

    def test_recipe_revision_cannot_be_mutated_by_application_role(self):
        service = HouseholdService(self.repo)
        recipe = service.recipe_library.save(example_recipe())
        with self.assertRaises(StorageUnavailable):
            with Database(self.app_conninfo).transaction(self.context) as conn:
                conn.execute("UPDATE menuagent.recipe_versions SET document = '{}'::jsonb WHERE recipe_id = %s", (recipe['id'],))
        self.assertEqual(service.recipe_library.revisions(recipe['id'])[0]['name'], recipe['name'])

    def test_recipe_editor_and_portion_calculator_survive_new_sessions(self):
        with self.ui_environment():
            app = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
            app.switch_page('application/ui/pages/recipes.py').run()
            self.button(app, 'Load example into editor').click().run()
            self.button(app, 'Save recipe').click().run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            saved = HouseholdService(self.repo).recipe_library.recipes
            self.assertEqual(len(saved), 1)
            reopened = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
            reopened.switch_page('application/ui/pages/recipes.py').run()
            self.assertFalse(reopened.exception)
            self.assertTrue(any(item.value == '1034.4 kcal' for item in reopened.metric))
            self.assertTrue(any(item.value == '258.6 kcal' for item in reopened.metric))
            next(item for item in reopened.selectbox if item.label == 'Recipe to edit').select(next(iter(saved))).run()
            next(item for item in reopened.text_input if item.label == 'Recipe name').input('Our chickpea bowl')
            self.button(reopened, 'Save recipe').click().run()
            self.assertFalse(reopened.exception)
            self.assertFalse(reopened.error)
            self.assertEqual(HouseholdService(self.repo).recipe_library.recipes[next(iter(saved))]['revision'], 2)

    def ui_environment(self):
        return patch.dict(os.environ, {'MENUAGENT_MODE': 'postgres', 'MENUAGENT_DATABASE_URL': self.app_conninfo,
                                      'MENUAGENT_HOUSEHOLD_ID': self.a, 'MENUAGENT_ACCESS_MODE': 'local',
                                      'MENUAGENT_LOCAL_EDITOR_SUBJECT': 'alice'})

    @staticmethod
    def button(app, label):
        return next(item for item in app.button if item.label == label)

    def test_all_pages_load_for_an_empty_persistent_household(self):
        with self.ui_environment():
            app = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
            self.assertFalse(app.exception)
            for name in ('household', 'groceries', 'recipes', 'history', 'week'):
                app.switch_page(f'application/ui/pages/{name}.py').run()
                self.assertFalse(app.exception, name)

    def test_profile_and_preferences_survive_new_streamlit_sessions(self):
        with self.ui_environment():
            app = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
            app.switch_page('application/ui/pages/household.py').run()
            next(item for item in app.text_input if item.label == 'New member name').input('Alex')
            self.button(app, 'Add member').click().run()
            next(item for item in app.checkbox if item.label == 'Use manually entered daily targets').check().run()
            for label, value in (('Calories (kcal/day)', 2100.0), ('Protein (g/day)', 125.0), ('Carbs (g/day)', 240.0), ('Fat (g/day)', 65.0)):
                next(item for item in app.number_input if item.label == label).set_value(value)
            self.button(app, 'Save member profile').click().run()
            next(item for item in app.multiselect if item.label == 'Usual cuisines').select('Indian')
            next(item for item in app.selectbox if item.label == 'Usual cooking effort').select('assembly')
            next(item for item in app.selectbox if item.label == 'Weekly meal-prep preference').select('none')
            next(item for item in app.multiselect if item.label == 'Usually busier days').select('Tuesday').select('Thursday')
            self.button(app, 'Save shared preferences').click().run()
            self.assertFalse(app.exception)
            reopened = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
            reopened.switch_page('application/ui/pages/household.py').run()
            self.assertFalse(reopened.exception)
            self.assertEqual(next(item.value for item in reopened.text_input if item.label == 'Name'), 'Alex')
            self.assertEqual(next(item.value for item in reopened.number_input if item.label == 'Protein (g/day)'), 125.0)
            self.assertEqual(reopened.multiselect[0].value, ['Indian'])
            self.assertEqual(next(item.value for item in reopened.selectbox if item.label == 'Usual cooking effort'), 'assembly')
            self.assertEqual(next(item.value for item in reopened.selectbox if item.label == 'Weekly meal-prep preference'), 'none')
            self.assertEqual(next(item.value for item in reopened.multiselect if item.label == 'Usually busier days'), ['Tuesday', 'Thursday'])
            reopened.switch_page('application/ui/pages/week.py').run()
            next(item for item in reopened.selectbox if item.label == 'Choose a day').select(1).run()
            self.assertFalse(reopened.exception)
            self.assertTrue(any('sample menu has not been adapted' in item.value for item in reopened.info))
            self.assertFalse(any('within budget' in item.value for item in reopened.markdown))

    def test_editor_revoke_blocks_rerun_before_displaying_profiles(self):
        service = HouseholdService(self.repo)
        service.add_member('Alex')
        with self.ui_environment():
            app = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
            with psycopg.connect(self.admin) as conn:
                conn.execute('DELETE FROM menuagent.editor_access WHERE household_id = %s', (self.a,))
            app.switch_page('application/ui/pages/household.py').run()
            self.assertFalse(app.exception)
            self.assertTrue(any('does not have access' in item.value for item in app.error))
            self.assertFalse(app.text_input)

    def test_week_overview_busy_days_save_and_sync_with_household(self):
        service = HouseholdService(self.repo)
        service.save_settings(['Indian'], 'simple', 'none', [])
        with self.ui_environment():
            app = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
            # Visit Household first to reproduce a previously rendered form.
            app.switch_page('application/ui/pages/household.py').run()
            app.switch_page('application/ui/pages/week.py').run()
            next(item for item in app.radio if item.label == 'Menu layout').set_value('Week overview').run()
            before_slots = [(slot.recipe_id, slot.locked) for slot in app.session_state['_household_service'].slots]
            key = 'profile-busy-days-editor-2026-10-12-'
            app.session_state[key] = {'edited_rows': {0: {'Busier day': True}, 4: {'Busier day': True}},
                                      'deleted_rows': [], 'added_rows': []}
            self.button(app, 'Save busier days').click().run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            saved = self.repo.read()
            self.assertEqual(saved.busy_days, ['Monday', 'Friday'])
            self.assertEqual((saved.cuisines, saved.cooking_effort, saved.meal_prep), (['Indian'], 'simple', 'none'))
            self.assertEqual(before_slots, [(slot.recipe_id, slot.locked) for slot in app.session_state['_household_service'].slots])
            app.switch_page('application/ui/pages/household.py').run()
            self.assertEqual(next(item.value for item in app.multiselect if item.label == 'Usually busier days'), ['Monday', 'Friday'])
            reopened = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
            self.assertEqual(reopened.session_state['_household_service'].busy_days, ['Monday', 'Friday'])
            # Unticking saved days must persist too.
            next(item for item in reopened.radio if item.label == 'Menu layout').set_value('Week overview').run()
            reopened.session_state[key + 'Monday-Friday'] = {'edited_rows': {0: {'Busier day': False}, 4: {'Busier day': False}},
                                                            'deleted_rows': [], 'added_rows': []}
            self.button(reopened, 'Save busier days').click().run()
            self.assertFalse(reopened.exception)
            self.assertEqual(self.repo.read().busy_days, [])

    def test_stock_editor_writes_survive_a_new_ui_session(self):
        with self.ui_environment():
            app = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
            app.switch_page('application/ui/pages/groceries.py').run()
            app.session_state['inventory-editor'] = {'edited_rows': {}, 'deleted_rows': [], 'added_rows': [
                {'Item': 'Yogurt', 'Location': 'Fridge', 'Quantity': 500.0, 'Unit': 'g', 'Status': 'Use soon'},
                {'Item': 'Olive oil', 'Location': 'Pantry', 'Quantity': None, 'Unit': 'ml', 'Status': 'Available'}]}
            self.button(app, 'Save stock changes').click().run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            self.assertEqual(self.repo.read().inventory[0]['Quantity'], 500.0)
            reopened = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
            reopened.switch_page('application/ui/pages/groceries.py').run()
            self.assertFalse(reopened.exception)
            self.assertEqual(reopened.session_state['_household_service'].inventory[0]['Item'], 'Yogurt')
            self.assertIsNone(reopened.session_state['_household_service'].inventory[1]['Quantity'])

    def test_oidc_mode_without_provider_fails_with_configuration_message(self):
        with self.ui_environment(), patch.dict(os.environ, {'MENUAGENT_ACCESS_MODE': 'oidc'}):
            app = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
            self.assertFalse(app.exception)
            self.assertTrue(any('Configure Streamlit' in item.value for item in app.error))

    def test_local_editor_mode_refuses_a_public_listener(self):
        old = st_config.get_option('server.address')
        st_config.set_option('server.address', '0.0.0.0')
        try:
            with self.ui_environment():
                app = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
                self.assertFalse(app.exception)
                self.assertTrue(any('loopback address' in item.value for item in app.error))
        finally:
            st_config.set_option('server.address', old)
