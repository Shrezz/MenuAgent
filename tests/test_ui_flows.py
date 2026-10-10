"""Exercise state changes through Streamlit's real widget/rerun lifecycle."""
from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "streamlit_app.py"


class UIFlowTests(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
        self.assertFalse(self.app.exception)

    def button(self, label):
        return next(item for item in self.app.button if item.label == label)

    def select(self, label):
        return next(item for item in self.app.selectbox if item.label == label)

    def test_member_edits_persist_when_switching_profiles(self):
        self.app.switch_page("application/ui/pages/household.py").run()
        next(item for item in self.app.text_input if item.label == "Name").input("Alex")
        next(item for item in self.app.number_input if item.label == "Protein (g/day)").set_value(125.0)
        self.button("Save member profile").click().run()
        service = self.app.session_state["_demo_service"]
        self.assertEqual(service.members[0].name, "Alex")
        self.assertEqual(service.members[0].targets["protein"], 125.0)

        self.select("Edit member").select("child").run()
        self.assertFalse(self.app.checkbox[0].value)
        self.select("Age group").select("Teen")
        self.button("Save member profile").click().run()
        self.select("Edit member").select("adult-a").run()
        self.select("Edit member").select("child").run()
        self.assertEqual(self.select("Age group").value, "Teen")
        self.assertIsNone(service.members[2].targets)
        self.assertFalse(self.app.exception)

    def test_receipt_confirmation_disables_repeat_submission(self):
        self.app.switch_page("application/ui/pages/groceries.py").run()
        self.button("Load sample receipt").click().run()
        self.button("Confirm sample purchases").click().run()
        self.assertTrue(self.button("Confirm sample purchases").disabled)
        service = self.app.session_state["_demo_service"]
        yogurt = next(row for row in service.inventory if row["Item"] == "Yogurt")
        self.assertEqual(yogurt["Quantity"], 1000.0)
        self.assertFalse(self.app.exception)

    def test_history_and_locks_survive_navigation_and_regeneration(self):
        self.button("Finalize preview").click().run()
        service = self.app.session_state["_demo_service"]
        self.assertEqual(len(service.history), 1)
        self.app.switch_page("application/ui/pages/history.py").run()
        self.assertEqual(len(self.app.dataframe), 1)
        self.app.switch_page("application/ui/pages/week.py").run()
        self.app.checkbox[0].check().run()
        recipe = service.slots[0].recipe_id
        self.button("Preview a fresh draft").click().run()
        self.assertEqual(service.slots[0].recipe_id, recipe)
        self.assertTrue(service.slots[0].locked)
        self.assertFalse(self.app.exception)


if __name__ == "__main__":
    unittest.main()
