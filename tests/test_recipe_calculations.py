from copy import deepcopy
import json
from math import inf
from pathlib import Path
import unittest
from unittest.mock import patch

from application.domain.nutrition import calculate_portion, calculate_recipe
from application.domain.planning import evaluate_menu
from application.domain.recipes import clean_recipe
from application.services.recipe_examples import example_recipe
from integrations.usda import USDAClient, USDAUnavailable, bundled_foods, match_candidates, parse_food


class RecipeCalculationTests(unittest.TestCase):
    def setUp(self):
        self.recipe = dict(example_recipe(), revision=1)
        self.member = {'id': 'adult', 'name': 'Alex', 'kind': 'Adult', 'targets': None, 'restrictions': ''}
        self.menu = {'version_id': 'candidate-1', 'meals': [{'id': 'dinner-0', 'day': 0, 'meal_type': 'Dinner', 'recipe_id': self.recipe['id'],
                    'recipe_revision': 1, 'batch_multiplier': 1, 'portions': [{'member_id': 'adult', 'servings': 1}]}]}
        self.inventory = [{'canonical_name': line['canonical_name'], 'state': line['state'], 'grams': 1000} for line in self.recipe['ingredients']]

    def evaluate(self, menu=None, recipe=None, members=None, inventory=None, settings=None):
        recipe = recipe or self.recipe
        return evaluate_menu(menu or self.menu, {recipe['id']: recipe}, members or [self.member], self.inventory if inventory is None else inventory,
                             settings or {}, expected_slots=[(0, 'Dinner')])

    def test_usda_snapshots_are_reproducible_from_recorded_responses(self):
        foods = bundled_foods()
        raw = json.loads((Path(__file__).resolve().parents[1] / 'integrations/data/usda_responses.json').read_text())
        for row in raw:
            stored = foods[f"fdc:{row['fdcId']}"]
            rebuilt = parse_food(row, stored['state'], stored['aliases'], stored['retrieved_at'])
            self.assertEqual(rebuilt, stored)

    def test_whole_recipe_and_serving_have_independently_expected_totals(self):
        whole = calculate_recipe(self.recipe)
        expected = {'kcal': 1034.4, 'protein': 38.44, 'carbs': 180.01, 'fat': 19.24}
        self.assertTrue(whole['complete'])
        portion = calculate_portion(self.recipe, {'servings': 1})
        for key, value in expected.items():
            self.assertAlmostEqual(whole['totals'][key], value)
            self.assertAlmostEqual(portion['totals'][key], value / 4)

    def test_missing_quantity_preserves_unknown_and_separate_known_subtotal(self):
        self.recipe['ingredients'][0]['quantity'] = None
        result = calculate_recipe(self.recipe)
        self.assertIsNone(result['totals']['kcal'])
        self.assertAlmostEqual(result['known_subtotals']['kcal'], 542.4)
        self.assertIn('unknown_quantity', [issue['code'] for issue in result['issues']])

    def test_missing_single_nutrient_does_not_hide_known_other_totals(self):
        self.recipe['ingredients'][0]['food']['nutrients']['protein'] = None
        result = calculate_recipe(self.recipe)
        self.assertIsNone(result['totals']['protein'])
        self.assertAlmostEqual(result['totals']['kcal'], 1034.4)
        self.assertFalse(result['complete'])

    def test_count_and_volume_need_reviewed_conversion(self):
        line = self.recipe['ingredients'][0]
        line.update(quantity=2, unit='each', grams_per_unit=None)
        self.assertFalse(calculate_recipe(self.recipe)['complete'])
        line.update(grams_per_unit=150, conversion_note='Measured drained portion, 150g each')
        self.assertAlmostEqual(calculate_recipe(clean_recipe(self.recipe))['totals']['kcal'], 1034.4)
        line['conversion_note'] = ''
        with self.assertRaises(ValueError):
            clean_recipe(self.recipe)

    def test_raw_cooked_mismatch_is_not_silently_used(self):
        self.recipe['ingredients'][0]['state'] = 'raw'
        result = calculate_recipe(self.recipe)
        self.assertIsNone(result['totals']['kcal'])
        self.assertIn('preparation_mismatch', [issue['code'] for issue in result['issues']])

    def test_gram_portions_need_explained_finished_yield(self):
        with self.assertRaises(ValueError):
            calculate_portion(self.recipe, {'grams': 100})
        self.recipe.update(cooked_yield_g=800, yield_note='Weighed after cooking')
        self.assertAlmostEqual(calculate_portion(clean_recipe(self.recipe), {'grams': 200})['totals']['kcal'], 258.6)

    def test_component_portions_change_shared_food_ratio(self):
        result = calculate_portion(self.recipe, {'component_fractions': {'Rice': 0.5, 'Chickpeas and vegetables': 0.25}})
        self.assertAlmostEqual(result['totals']['kcal'], 356.1)
        with self.assertRaises(ValueError):
            calculate_portion(self.recipe, {'servings': 1, 'grams': 200})

    def test_invalid_recipe_numbers_and_source_units_are_rejected(self):
        for value in (-1, 0, True, inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                clean_recipe(dict(self.recipe, servings=value))
        raw = {'fdcId': 123, 'description': 'Fixture', 'foodNutrients': [{'nutrient': {'id': 1008, 'unitName': 'kJ'}, 'amount': 100}]}
        food = parse_food(raw, 'raw')
        self.assertIsNone(food['nutrients']['kcal'])

    def test_normalized_aliases_require_preparation_review(self):
        candidates = match_candidates(bundled_foods(), '  CHICKPEAS ')
        self.assertEqual({food['state'] for food in candidates}, {'raw', 'cooked'})
        self.assertEqual(len(match_candidates(bundled_foods(), 'chickpeas', 'cooked')), 1)
        self.recipe['ingredients'][0]['name'] = 'Garbanzo beans'
        self.assertEqual(clean_recipe(self.recipe)['ingredients'][0]['canonical_name'], 'chickpeas')

    def test_live_lookup_without_key_is_explicit_and_sanitized(self):
        with patch.dict('os.environ', {}, clear=True), self.assertRaises(USDAUnavailable) as caught:
            USDAClient().search('rice')
        self.assertIn('backend environment', str(caught.exception))

    def test_checked_candidate_totals_and_fingerprint_change_with_portions(self):
        first = self.evaluate()
        self.assertTrue(first['ready'])
        self.assertEqual(first['candidate_version_id'], 'candidate-1')
        self.assertAlmostEqual(first['daily_totals'][0]['totals']['kcal'], 258.6)
        revised = deepcopy(self.menu)
        revised['version_id'] = 'candidate-2'
        revised['meals'][0]['portions'][0]['servings'] = 2
        second = self.evaluate(menu=revised)
        self.assertNotEqual(first['input_fingerprint'], second['input_fingerprint'])
        self.assertAlmostEqual(second['daily_totals'][0]['totals']['kcal'], 517.2)

    def test_recipe_revision_and_duplicate_dish_are_required_checks(self):
        menu = deepcopy(self.menu)
        menu['meals'][0]['recipe_revision'] = 0
        self.assertIn('stale_recipe', [issue['code'] for issue in self.evaluate(menu=menu)['issues']])
        other = deepcopy(menu['meals'][0]); other.update(id='dinner-1', day=1)
        menu['meals'].append(other)
        result = self.evaluate(menu=menu)
        self.assertFalse(result['ready'])
        self.assertIn('duplicate_dish', [issue['code'] for issue in result['issues']])

    def test_shared_component_portions_cannot_exceed_prepared_batch(self):
        self.menu['meals'][0]['portions'][0]['servings'] = 5
        result = self.evaluate()
        self.assertFalse(result['ready'])
        self.assertIn('portion_overallocation', [issue['code'] for issue in result['issues']])

    def test_restrictions_need_review_and_conflicts_are_blocked(self):
        member = dict(self.member, restrictions='milk')
        self.assertIn('restriction_review_needed', [issue['code'] for issue in self.evaluate(members=[member])['issues']])
        self.recipe.update(restriction_reviewed=True, allergens=['milk'])
        self.assertIn('allergen_conflict', [issue['code'] for issue in self.evaluate(members=[member])['issues']])
        self.assertIn('unrecognized_restriction', [issue['code'] for issue in self.evaluate(members=[dict(self.member, restrictions='Low histamine')])['issues']])

    def test_children_have_no_invented_targets_and_busy_day_time_is_not_hard_limit(self):
        child = dict(self.member, kind='Child')
        result = self.evaluate(members=[child], settings={'busy_day_indices': [0]})
        self.assertIsNone(result['daily_totals'][0]['target_differences'])
        self.assertIn('child_balance_review', [issue['code'] for issue in result['issues']])
        self.recipe.update(effort='involved', active_minutes=999)
        result = self.evaluate(settings={'busy_day_indices': [0]})
        self.assertTrue(result['ready'])
        self.assertEqual(next(issue['severity'] for issue in result['issues'] if issue['code'] == 'busy_day_effort'), 'recommendation')

    def test_unknown_stock_is_not_zero_and_known_shortfalls_are_explicit(self):
        result = self.evaluate(inventory=[])
        self.assertFalse(result['ready'])
        self.assertIsNone(result['shopping'][0]['available_g'])
        inventory = [dict(row, grams=1) for row in self.inventory]
        result = self.evaluate(inventory=inventory)
        self.assertIn('stock_shortfall', [issue['code'] for issue in result['issues']])
        allowed = self.evaluate(inventory=inventory, settings={'allow_shopping': True})
        self.assertTrue(allowed['ready'])
        self.assertIn('purchase_needed', [issue['code'] for issue in allowed['issues']])

    def test_missing_portions_or_nutrients_prevent_ready_status(self):
        self.menu['meals'][0]['portions'] = []
        self.assertFalse(self.evaluate()['ready'])
        self.assertIn('missing_portions', [issue['code'] for issue in self.evaluate()['issues']])
        self.recipe['ingredients'][0]['food'] = None
        self.assertIn('unmatched_food', [issue['code'] for issue in self.evaluate()['issues']])

    def test_complete_seven_day_fixture_and_duplicate_slot_detection(self):
        # Synthetic dish identities test the contract; these are not a suggested menu.
        recipes, meals = {}, []
        meal_types = ('Breakfast', 'Lunch', 'Dinner', 'Snack')
        for day in range(7):
            for meal_type in meal_types:
                identity = f'fixture-{day}-{meal_type}'
                recipe = dict(deepcopy(self.recipe), id=identity, dish_family=identity, meal_type=meal_type)
                recipes[identity] = recipe
                meals.append({'id': identity, 'day': day, 'meal_type': meal_type, 'recipe_id': identity,
                              'recipe_revision': 1, 'batch_multiplier': 1, 'portions': [{'member_id': 'adult', 'servings': 1}]})
        menu = {'version_id': 'week-fixture', 'meals': meals}
        inventory = [dict(row, grams=100000) for row in self.inventory]
        result = evaluate_menu(menu, recipes, [self.member], inventory)
        self.assertTrue(result['ready'])
        self.assertEqual(len(result['daily_totals']), 7)
        self.assertAlmostEqual(result['daily_totals'][0]['totals']['kcal'], 1034.4)
        meals[-1]['day'] = 0
        self.assertFalse(evaluate_menu(menu, recipes, [self.member], inventory)['ready'])

    def test_invalid_stock_and_missing_version_do_not_pass(self):
        result = self.evaluate(inventory=[dict(row, grams=-100) for row in self.inventory])
        self.assertFalse(result['ready'])
        self.assertIn('invalid_stock_quantity', [issue['code'] for issue in result['issues']])
        self.menu['version_id'] = None
        self.assertIn('missing_candidate_version', [issue['code'] for issue in self.evaluate()['issues']])
