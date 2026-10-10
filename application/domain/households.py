"""Validation shared by the preview UI and durable household services."""
from dataclasses import replace
from math import isfinite, isnan

from application.domain.models import Member

CUISINES = ("Indian", "South Indian", "Mediterranean", "Mexican", "East Asian", "Italian", "Everyday")
AGE_GROUPS = ("Toddler", "Preschool", "School age", "Teen")
LOCATIONS = ("Fridge", "Pantry", "Freezer")
UNITS = ("g", "ml", "each")
STOCK_STATUSES = ("Available", "Use soon", "Low", "Out")
TARGET_KEYS = ("kcal", "protein", "carbs", "fat")
COOKING_EFFORTS = {
    "assembly": "Mostly assembly or reheating",
    "simple": "Simple cooking",
    "flexible": "Comfortable with more involved meals",
}
MEAL_PREP_PREFERENCES = {
    "none": "No weekly meal prep",
    "small": "A small prep session",
    "larger": "A larger weekly prep session",
}
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def clean_member(member: Member) -> Member:
    name = str(member.name).strip()
    if not name or len(name) > 120:
        raise ValueError("Enter a member name of up to 120 characters.")
    if member.kind not in ("Adult", "Child"):
        raise ValueError("Choose Adult or Child.")
    if member.kind == "Child" and member.age_group not in AGE_GROUPS:
        raise ValueError("Choose an age group for the child.")
    targets = None
    if member.targets is not None:
        if set(member.targets) != set(TARGET_KEYS):
            raise ValueError("Enter all four daily targets, or turn off manual targets.")
        targets = {}
        for key in TARGET_KEYS:
            value = member.targets[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
                raise ValueError("Daily targets must be positive, finite numbers.")
            targets[key] = float(value)
    return replace(member, name=name, age_group=member.age_group if member.kind == "Child" else "", targets=targets,
                   dislikes=str(member.dislikes).strip(), restrictions=str(member.restrictions).strip())


def clean_settings(cuisines, cooking_effort, meal_prep, busy_days):
    if any(value not in CUISINES for value in cuisines) or len(set(cuisines)) != len(cuisines):
        raise ValueError("Choose distinct cuisines from the available list.")
    if cooking_effort is not None and cooking_effort not in COOKING_EFFORTS:
        raise ValueError("Choose a supported cooking effort.")
    if meal_prep is not None and meal_prep not in MEAL_PREP_PREFERENCES:
        raise ValueError("Choose a supported meal-prep preference.")
    if any(day not in WEEKDAYS for day in busy_days) or len(set(busy_days)) != len(busy_days):
        raise ValueError("Choose distinct weekdays for busier days.")
    return list(cuisines), cooking_effort, meal_prep, [day for day in WEEKDAYS if day in busy_days]


def clean_inventory(rows):
    result, seen = [], set()
    for row in rows:
        raw_name = row.get("Item")
        if raw_name is None or not str(raw_name).strip():
            # Ignore only empty editor rows; never discard entered quantities.
            quantity = row.get("Quantity")
            if quantity is not None and not (isinstance(quantity, float) and isnan(quantity)):
                raise ValueError("Enter an ingredient name for every quantity.")
            continue
        name = " ".join(str(raw_name).split())
        if len(name) > 160:
            raise ValueError("Ingredient names must be at most 160 characters.")
        location, unit, status = row.get("Location") or "Pantry", row.get("Unit") or "g", row.get("Status") or "Available"
        if location not in LOCATIONS or unit not in UNITS or status not in STOCK_STATUSES:
            raise ValueError("Choose a supported location, unit and stock status.")
        quantity = row.get("Quantity")
        if quantity is not None:
            if isinstance(quantity, bool):
                raise ValueError("Quantities must be numbers or left blank.")
            try:
                quantity = float(quantity)
            except (TypeError, ValueError):
                raise ValueError("Quantities must be numbers or left blank.") from None
            if isnan(quantity):
                quantity = None  # Streamlit's blank numeric cells.
            elif not isfinite(quantity) or quantity < 0:
                raise ValueError("Quantities must be finite, non-negative numbers.")
        key = (name.casefold(), location, unit)
        if key in seen:
            raise ValueError("Combine duplicate ingredient rows with the same location and unit.")
        seen.add(key)
        result.append({"Item": name, "Location": location, "Quantity": quantity, "Unit": unit, "Status": status})
    return result
