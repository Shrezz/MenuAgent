"""Pure application-backed tools for the future planner runtime."""
from application.domain.nutrition import calculate_portion, calculate_recipe
from application.domain.planning import evaluate_menu


def calculate_nutrition(recipe, portion=None):
    return calculate_portion(recipe, portion) if portion is not None else calculate_recipe(recipe)


def validate_menu(menu, recipes, members, inventory=(), settings=None, expected_slots=None):
    return evaluate_menu(menu, recipes, members, inventory, settings, expected_slots)
