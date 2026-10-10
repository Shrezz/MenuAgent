"""Integration tests create and remove their own database, never the app's data."""
from dataclasses import replace
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
from database.connection import AccessDenied, ConcurrentChange, Database, EditorContext, StorageUnavailable
from database.manage import bootstrap_household, grant_app_role, migrate

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
        self.assertEqual(count, 1)

    def test_profiles_preferences_and_stock_survive_a_new_service(self):
        service = HouseholdService(self.repo)
        service.add_member('Alex')
        adult = service.members[0]
        service.save_member(replace(adult, targets={'kcal': 2100, 'protein': 125, 'carbs': 240, 'fat': 65}, restrictions='Peanuts'))
        service.add_member('Sam', 'Child', 'School age')
        service.save_settings(['Indian', 'Mediterranean'], 45, 60)
        service.save_inventory([{'Item': 'Yogurt', 'Location': 'Fridge', 'Quantity': 500, 'Unit': 'g'}, {'Item': 'Olive oil', 'Quantity': None, 'Unit': 'ml'}])
        reopened = HouseholdService(HouseholdRepository(Database(self.app_conninfo), self.context))
        by_name = {member.name: member for member in reopened.members}
        self.assertEqual(by_name['Alex'].targets['protein'], 125)
        self.assertEqual(by_name['Alex'].restrictions, 'Peanuts')
        self.assertIsNone(by_name['Sam'].targets)
        self.assertEqual(reopened.cuisines, ['Indian', 'Mediterranean'])
        self.assertEqual((reopened.daily_minutes, reopened.batch_minutes), (45, 60))
        self.assertIsNone(reopened.inventory[1]['Quantity'])
        self.assertEqual(self.other.read().members, [])

    def test_forged_household_or_unknown_editor_cannot_read_or_write(self):
        for context in (EditorContext(self.b, 'alice'), EditorContext(self.a, 'outsider')):
            repository = HouseholdRepository(Database(self.app_conninfo), context)
            with self.assertRaises(AccessDenied):
                repository.read()
            with self.assertRaises(AccessDenied):
                repository.save_settings(['Indian'], 45, 60, 1)
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
        first.save_settings(['Indian'], 45, 60)
        with self.assertRaises(ConcurrentChange):
            stale.save_settings(['Mexican'], 90, 90)
        self.assertEqual(self.repo.read().cuisines, ['Indian'])
        stale.refresh()
        stale.save_settings(['Mexican'], 45, 60)
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
            self.repo.save_settings(['Mexican'], 45, 60, version)
            return version

        with patch.object(self.repo, 'save_member', side_effect=interleaved_save):
            service.add_member('Alex')
        self.assertEqual(service.household_version, 2)
        with self.assertRaises(ConcurrentChange):
            service.save_settings(['Indian'], 45, 60)
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
            next(item for item in app.number_input if item.label == 'Daily active cooking budget (min)').set_value(45)
            next(item for item in app.number_input if item.label == 'Sunday batch preparation budget (min)').set_value(60)
            self.button(app, 'Save shared preferences').click().run()
            self.assertFalse(app.exception)
            reopened = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
            reopened.switch_page('application/ui/pages/household.py').run()
            self.assertFalse(reopened.exception)
            self.assertEqual(next(item.value for item in reopened.text_input if item.label == 'Name'), 'Alex')
            self.assertEqual(next(item.value for item in reopened.number_input if item.label == 'Protein (g/day)'), 125.0)
            self.assertEqual(reopened.multiselect[0].value, ['Indian'])

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
