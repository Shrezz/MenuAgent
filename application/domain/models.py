"""UI preview records. Sourced nutrition and database records arrive next."""
from dataclasses import dataclass, field

MEAL_TYPES = ("Breakfast", "Lunch", "Dinner", "Snack")


@dataclass(frozen=True)
class Recipe:
    id: str
    name: str
    meal_type: str
    cuisine: str
    active_minutes: int
    ingredients: tuple[str, ...]
    prep_component: str = ""
    freezer_friendly: bool = False
    is_new: bool = False


@dataclass
class Member:
    id: str
    name: str
    kind: str = "Adult"
    age_group: str = ""
    targets: dict[str, float] | None = None
    dislikes: str = ""
    restrictions: str = ""


@dataclass
class MealSlot:
    day: int
    meal_type: str
    recipe_id: str
    locked: bool = False
    portion_shares: dict[str, float] = field(default_factory=dict)
