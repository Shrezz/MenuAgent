import unittest
from copy import deepcopy
from application.services.demo import DemoService


class DemoServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = DemoService()

    def test_fresh_draft_preserves_locks_and_weekly_uniqueness(self):
        self.service.slots[0].locked = True
        locked_recipe = self.service.slots[0].recipe_id
        self.service.fresh_draft()
        self.assertEqual(self.service.slots[0].recipe_id, locked_recipe)
        self.assertTrue(self.service.preview_checks()["All 28 meal slots filled"])
        self.assertTrue(self.service.preview_checks()["No repeated finished dishes"])

    def test_receipt_confirmation_is_idempotent(self):
        original = deepcopy(self.service.inventory)
        self.assertTrue(self.service.confirm_sample_receipt(self.service.receipt_items))
        after = deepcopy(self.service.inventory)
        self.assertFalse(self.service.confirm_sample_receipt(self.service.receipt_items))
        self.assertEqual(after, self.service.inventory)
        before_yogurt = next(row for row in original if row["Item"] == "Yogurt")
        after_yogurt = next(row for row in after if row["Item"] == "Yogurt")
        self.assertEqual(after_yogurt["Quantity"], before_yogurt["Quantity"] + 500)

    def test_receipt_with_invalid_quantity_does_not_partially_commit(self):
        original = deepcopy(self.service.inventory)
        invalid = deepcopy(self.service.receipt_items)
        invalid[-1]["Quantity"] = -2
        with self.assertRaises(ValueError):
            self.service.confirm_sample_receipt(invalid)
        self.assertEqual(original, self.service.inventory)
        self.assertFalse(self.service.confirmed_receipts)

    def test_history_is_immutable_when_current_menu_changes(self):
        self.service.finalize_preview()
        saved_recipe = self.service.history[0]["slots"][0].recipe_id
        alternative = next(recipe for recipe in self.service.alternatives(0) if recipe.id != saved_recipe)
        self.service.swap(0, alternative.id)
        self.assertEqual(self.service.history[0]["slots"][0].recipe_id, saved_recipe)
        self.assertNotEqual(self.service.slots[0].recipe_id, saved_recipe)

    def test_locked_or_duplicate_swaps_are_rejected(self):
        self.service.slots[0].locked = True
        with self.assertRaises(ValueError):
            self.service.swap(0, "breakfast-7")
        self.service.slots[0].locked = False
        with self.assertRaises(ValueError):
            self.service.swap(0, self.service.slots[4].recipe_id)


if __name__ == "__main__":
    unittest.main()
