from dataclasses import replace
from math import inf, nan
import unittest

from application.domain.households import clean_inventory, clean_member, clean_settings
from application.domain.models import Member


class HouseholdValidationTests(unittest.TestCase):
    def test_child_has_no_automatic_numeric_targets(self):
        member = clean_member(Member('child', ' Sam ', 'Child', 'School age'))
        self.assertEqual(member.name, 'Sam')
        self.assertIsNone(member.targets)

    def test_targets_require_all_positive_finite_values(self):
        valid = Member('adult', 'Alex', targets={'kcal': 2000, 'protein': 120, 'carbs': 230, 'fat': 65})
        for value in (0, -1, inf, nan, True, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                clean_member(replace(valid, targets=dict(valid.targets, protein=value)))
        with self.assertRaises(ValueError):
            clean_member(replace(valid, targets={'kcal': 2000}))

    def test_profile_modes_and_child_age_are_validated(self):
        for member in (Member('x', ''), Member('x', 'Sam', 'Child', ''), Member('x', 'Sam', 'Unknown')):
            with self.assertRaises(ValueError):
                clean_member(member)

    def test_untracked_staples_remain_unknown(self):
        rows = [{'Item': ' Olive   oil ', 'Quantity': None, 'Unit': 'ml'}, {'Item': 'Salt', 'Quantity': nan}]
        cleaned = clean_inventory(rows)
        self.assertEqual(cleaned[0]['Item'], 'Olive oil')
        self.assertIsNone(cleaned[0]['Quantity'])
        self.assertIsNone(cleaned[1]['Quantity'])

    def test_inventory_rejects_invalid_units_and_nonfinite_quantities(self):
        invalid = [{'Item': 'Rice', 'Quantity': inf}, {'Item': 'Rice', 'Quantity': -1},
                   {'Item': 'Rice', 'Unit': 'buckets'}, {'Item': 'Rice', 'Location': 'Garage'}, {'Item': '', 'Quantity': 500}]
        for row in invalid:
            with self.subTest(row=row), self.assertRaises(ValueError):
                clean_inventory([row])

    def test_duplicate_stock_rows_do_not_silently_double_count(self):
        with self.assertRaises(ValueError):
            clean_inventory([{'Item': 'Rice', 'Quantity': 500}, {'Item': ' rice ', 'Quantity': 200}])

    def test_settings_allow_unentered_budgets_and_validate_entered_values(self):
        self.assertEqual(clean_settings([], None, None), ([], None, None))
        for args in ((['Unlisted'], 45, 60), (['Indian'], -1, 60), (['Indian'], 45, 181), (['Indian'], True, 60)):
            with self.assertRaises(ValueError):
                clean_settings(*args)
