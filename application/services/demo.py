"""Session-only application service used to review the UI before integrations."""
from copy import deepcopy
from datetime import date
from uuid import uuid4

from application.domain.households import clean_inventory, clean_member, clean_settings
from application.domain.models import MEAL_TYPES, MealSlot, Member, Recipe


def sample_recipes() -> dict[str, Recipe]:
    groups = {
        "Breakfast": [
            ("Vegetable poha", "Indian", 8, ("flattened rice", "peas", "onion"), ""),
            ("Vegetable upma", "South Indian", 10, ("semolina", "carrot", "peas"), ""),
            ("Overnight oats", "Everyday", 3, ("oats", "yogurt", "berries"), ""),
            ("Egg and spinach toast", "Everyday", 6, ("eggs", "spinach", "bread"), ""),
            ("Idli and coconut chutney", "South Indian", 5, ("idli batter", "coconut"), ""),
            ("Yogurt and fruit bowl", "Everyday", 3, ("yogurt", "pear", "oats"), ""),
            ("Chickpea flour pancakes", "Indian", 10, ("chickpea flour", "tomato", "onion"), ""),
            ("Avocado toast", "Everyday", 5, ("avocado", "bread", "lemon"), ""),
            ("Savory oat pancakes", "Everyday", 8, ("oats", "eggs", "spinach"), ""),
        ],
        "Lunch": [
            ("Lemon chickpea salad", "Mediterranean", 8, ("chickpeas", "cucumber", "lemon"), "Plain chickpeas"),
            ("Lentil and rice bowl", "Indian", 12, ("lentils", "rice", "carrot"), "Tomato-onion base"),
            ("Paneer vegetable wrap", "Indian", 10, ("paneer", "tortilla", "pepper"), "Chopped vegetables"),
            ("Vegetable couscous", "Mediterranean", 8, ("couscous", "peas", "carrot"), "Chopped vegetables"),
            ("Black bean tacos", "Mexican", 12, ("black beans", "tortilla", "tomato"), ""),
            ("Spinach dal with rice", "Indian", 10, ("lentils", "spinach", "rice"), "Tomato-onion base"),
            ("Tomato soup and toast", "Everyday", 12, ("tomato", "bread", "onion"), ""),
            ("Chickpea vegetable wrap", "Mediterranean", 8, ("chickpeas", "tortilla", "cucumber"), "Plain chickpeas"),
            ("Pea and rice salad", "Everyday", 8, ("rice", "peas", "lemon"), ""),
        ],
        "Dinner": [
            ("Chickpea curry, rice and beans", "Indian", 22, ("chickpeas", "rice", "green beans"), "Plain chickpeas"),
            ("Lemon chicken and potatoes", "Mediterranean", 20, ("chicken", "potatoes", "lemon"), ""),
            ("Tofu vegetable stir-fry", "East Asian", 15, ("tofu", "broccoli", "rice"), "Chopped vegetables"),
            ("Rajma with rice", "Indian", 20, ("kidney beans", "tomato", "rice"), "Tomato-onion base"),
            ("Pea and ricotta pasta", "Italian", 18, ("pasta", "peas", "ricotta"), ""),
            ("Vegetable khichdi and raita", "Indian", 15, ("rice", "lentils", "yogurt"), "Chopped vegetables"),
            ("Fish and vegetable tray bake", "Mediterranean", 20, ("fish", "potatoes", "carrot"), ""),
            ("Lentil vegetable stew", "Mediterranean", 18, ("lentils", "tomato", "carrot"), "Tomato-onion base"),
            ("Vegetable fried rice", "East Asian", 12, ("rice", "eggs", "peas"), "Chopped vegetables"),
        ],
        "Snack": [
            ("Apple and yogurt", "Everyday", 2, ("apple", "yogurt"), ""),
            ("Pear and cottage cheese", "Everyday", 2, ("pear", "cottage cheese"), ""),
            ("Hummus and pita", "Mediterranean", 2, ("hummus", "pita"), ""),
            ("Banana and milk", "Everyday", 2, ("banana", "milk"), ""),
            ("Berries and yogurt", "Everyday", 2, ("berries", "yogurt"), ""),
            ("Orange and cheese", "Everyday", 2, ("orange", "cheese"), ""),
            ("Peach and cottage cheese", "Everyday", 2, ("peach", "cottage cheese"), ""),
            ("Grapes and yogurt", "Everyday", 2, ("grapes", "yogurt"), ""),
            ("Melon and milk", "Everyday", 2, ("melon", "milk"), ""),
        ],
    }
    result = {}
    for meal_type, rows in groups.items():
        for index, (name, cuisine, minutes, ingredients, component) in enumerate(rows):
            recipe_id = f"{meal_type.lower()}-{index}"
            result[recipe_id] = Recipe(
                recipe_id, name, meal_type, cuisine, minutes, ingredients, component,
                freezer_friendly=meal_type == "Dinner" and index in (0, 3, 7),
                is_new=index in (7, 8),
            )
    return result


class DemoService:
    """The UI calls this facade; a persistent service can replace it later."""

    persistent = False

    def __init__(self):
        self.recipes = sample_recipes()
        self.week_start = date(2026, 10, 12)
        self.revision = 1
        self.status = "Draft preview"
        self.cooking_effort = "simple"
        self.meal_prep = "small"
        self.busy_days = []
        self.cuisines = ["Indian", "Mediterranean", "Mexican"]
        self.members = [
            Member("adult-a", "Adult A", targets={"kcal": 2000.0, "protein": 120.0, "carbs": 230.0, "fat": 65.0}),
            Member("adult-b", "Adult B", targets={"kcal": 2400.0, "protein": 140.0, "carbs": 280.0, "fat": 75.0}),
            Member("child", "Child", kind="Child", age_group="School age", targets=None),
        ]
        self.slots = [
            MealSlot(day, meal_type, f"{meal_type.lower()}-{day}")
            for day in range(7) for meal_type in MEAL_TYPES
        ]
        self.inventory = [
            {"Item": "Chickpeas", "Location": "Pantry", "Quantity": 800.0, "Unit": "g", "Status": "Available"},
            {"Item": "Rice", "Location": "Pantry", "Quantity": 2000.0, "Unit": "g", "Status": "Available"},
            {"Item": "Yogurt", "Location": "Fridge", "Quantity": 500.0, "Unit": "g", "Status": "Use soon"},
            {"Item": "Spinach", "Location": "Fridge", "Quantity": 200.0, "Unit": "g", "Status": "Use soon"},
            {"Item": "Peas", "Location": "Freezer", "Quantity": 500.0, "Unit": "g", "Status": "Available"},
            {"Item": "Olive oil", "Location": "Pantry", "Quantity": None, "Unit": "ml", "Status": "Available"},
        ]
        self.receipt_items = [
            {"Item": "Tomatoes", "Location": "Fridge", "Quantity": 700.0, "Unit": "g", "Status": "Available"},
            {"Item": "Yogurt", "Location": "Fridge", "Quantity": 500.0, "Unit": "g", "Status": "Available"},
            {"Item": "Onions", "Location": "Pantry", "Quantity": 1000.0, "Unit": "g", "Status": "Available"},
            {"Item": "Bananas", "Location": "Pantry", "Quantity": 6.0, "Unit": "each", "Status": "Available"},
        ]
        self.confirmed_receipts = set()
        self.history = []
        self.ratings = {}

    def day_slots(self, day):
        return [(index, slot) for index, slot in enumerate(self.slots) if slot.day == day]

    def active_minutes(self, day):
        return sum(self.recipes[slot.recipe_id].active_minutes for _, slot in self.day_slots(day))

    def preview_checks(self):
        expected = {(day, meal_type) for day in range(7) for meal_type in MEAL_TYPES}
        actual = {(slot.day, slot.meal_type) for slot in self.slots}
        recipe_ids = [slot.recipe_id for slot in self.slots]
        return {
            "All 28 meal slots filled": len(self.slots) == 28 and expected == actual,
            "No repeated finished dishes": len(set(recipe_ids)) == len(recipe_ids),
        }

    def alternatives(self, slot_index):
        slot = self.slots[slot_index]
        used = {item.recipe_id for index, item in enumerate(self.slots) if index != slot_index}
        return [
            recipe for recipe in self.recipes.values()
            if recipe.meal_type == slot.meal_type and recipe.id not in used
        ]

    def swap(self, slot_index, recipe_id):
        slot = self.slots[slot_index]
        if slot.locked:
            raise ValueError("Unlock this meal before changing it.")
        if recipe_id not in {recipe.id for recipe in self.alternatives(slot_index)}:
            raise ValueError("Choose an unused recipe for the same meal type.")
        slot.recipe_id = recipe_id
        self.revision += 1
        self.status = "Draft preview"

    def fresh_draft(self):
        used = {slot.recipe_id for slot in self.slots if slot.locked}
        candidates = []
        for slot in self.slots:
            if slot.locked:
                candidates.append(slot.recipe_id)
                continue
            choices = [
                recipe.id for recipe in self.recipes.values()
                if recipe.meal_type == slot.meal_type and recipe.id not in used
            ]
            if not choices:
                raise ValueError("There are not enough distinct sample recipes.")
            chosen = choices[self.revision % len(choices)]
            candidates.append(chosen)
            used.add(chosen)
        for slot, recipe_id in zip(self.slots, candidates):
            slot.recipe_id = recipe_id
        self.revision += 1
        self.status = "Draft preview"

    def finalize_preview(self):
        if not all(self.preview_checks().values()):
            raise ValueError("Resolve the preview checks before finalizing.")
        key = f"{self.week_start.isoformat()}:{self.revision}"
        if not any(item["key"] == key for item in self.history):
            self.history.append({
                "key": key,
                "week_start": self.week_start,
                "revision": self.revision,
                "slots": deepcopy(self.slots),
                "recipe_names": {recipe.id: recipe.name for recipe in self.recipes.values()},
            })
        self.status = "Finalized preview"

    @staticmethod
    def clean_inventory(rows):
        return clean_inventory(rows)

    def add_member(self, name, kind="Adult", age_group=""):
        self.save_member(Member(str(uuid4()), name, kind, age_group))

    def save_member(self, member):
        cleaned = clean_member(member)
        index = next((i for i, item in enumerate(self.members) if item.id == cleaned.id), None)
        if index is None:
            self.members.append(cleaned)
        else:
            self.members[index] = cleaned

    def save_settings(self, cuisines, cooking_effort, meal_prep, busy_days):
        self.cuisines, self.cooking_effort, self.meal_prep, self.busy_days = clean_settings(cuisines, cooking_effort, meal_prep, busy_days)

    def save_inventory(self, rows):
        self.inventory = clean_inventory(rows)

    def confirm_sample_receipt(self, rows):
        receipt_id = "sample-receipt-v1"
        if receipt_id in self.confirmed_receipts:
            return False
        additions = self.clean_inventory(rows)
        updated = deepcopy(self.inventory)
        for addition in additions:
            match = next((
                item for item in updated
                if item["Item"].casefold() == addition["Item"].casefold()
                and item["Unit"] == addition["Unit"]
                and item["Location"] == addition["Location"]
            ), None)
            if match and match["Quantity"] is not None and addition["Quantity"] is not None:
                match["Quantity"] += addition["Quantity"]
            else:
                updated.append(addition)
        self.inventory = updated
        self.confirmed_receipts.add(receipt_id)
        return True

    @property
    def recipe_library(self):
        from application.services.recipes import RecipeLibrary
        if not hasattr(self, '_recipe_library'):
            self._recipe_library = RecipeLibrary(self)
        return self._recipe_library
