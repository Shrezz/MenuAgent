"""Durable household data alongside explicitly session-only menu previews."""
from uuid import uuid4

from application.domain.households import clean_inventory, clean_member, clean_settings
from application.domain.models import Member
from application.repositories.households import HouseholdRepository
from application.services.demo import DemoService


class HouseholdService(DemoService):
    persistent = True

    def __init__(self, repository: HouseholdRepository):
        super().__init__()
        self.repository = repository
        self.refresh()

    def refresh(self):
        snapshot = self.repository.read()
        self.household_name = snapshot.name
        self.household_version = snapshot.version
        self.members, self.inventory = snapshot.members, snapshot.inventory
        self.cuisines = snapshot.cuisines
        self.cooking_effort, self.meal_prep, self.busy_days = snapshot.cooking_effort, snapshot.meal_prep, snapshot.busy_days
        if hasattr(self, "_recipe_library"):
            self._recipe_library.refresh()

    def add_member(self, name, kind="Adult", age_group=""):
        self.save_member(Member(str(uuid4()), name, kind, age_group))

    # Keep the exact committed version. A read after a write could adopt another
    # editor's newer version while old form inputs still remain on screen.
    def save_member(self, member):
        member = clean_member(member)
        version = self.repository.save_member(member, self.household_version)
        super().save_member(member)
        self.household_version = version

    def save_settings(self, cuisines, cooking_effort, meal_prep, busy_days):
        cuisines, cooking_effort, meal_prep, busy_days = clean_settings(cuisines, cooking_effort, meal_prep, busy_days)
        version = self.repository.save_settings(cuisines, cooking_effort, meal_prep, busy_days, self.household_version)
        self.cuisines, self.cooking_effort, self.meal_prep, self.busy_days = cuisines, cooking_effort, meal_prep, busy_days
        self.household_version = version

    def save_inventory(self, rows):
        cleaned = clean_inventory(rows)
        version = self.repository.save_inventory(cleaned, self.household_version)
        self.inventory = cleaned
        self.household_version = version

    def confirm_sample_receipt(self, rows):
        raise ValueError("Sample receipts can only update the preview household. Enter actual purchases in Kitchen stock.")
