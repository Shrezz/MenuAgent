"""Original editor examples; never automatically seed a household."""
from uuid import uuid4
from application.domain.recipes import clean_recipe
from integrations.usda import bundled_foods


def example_recipe():
    foods = bundled_foods()
    lines = [
        ('Chickpeas', 300.0, 'cooked', 'fdc:173757', 'Chickpeas and vegetables'),
        ('Carrots', 100.0, 'raw', 'fdc:170393', 'Chickpeas and vegetables'),
        ('Spinach', 100.0, 'raw', 'fdc:168462', 'Chickpeas and vegetables'),
        ('Olive oil', 10.0, 'as sold', 'fdc:171413', 'Chickpeas and vegetables'),
        ('Rice', 300.0, 'cooked', 'fdc:168878', 'Rice'),
    ]
    return clean_recipe({'id': str(uuid4()), 'name': 'Chickpea and vegetable rice bowl', 'dish_family': 'chickpea vegetable rice bowl',
                         'meal_type': 'Dinner', 'cuisine': 'Everyday', 'servings': 4, 'cooked_yield_g': None, 'yield_note': '',
                         'source_label': 'MenuAgent original example; review before using', 'source_url': '',
                         'effort': 'simple', 'active_minutes': None, 'equipment': ['Pan'],
                         'instructions': ['Use cooked chickpeas and cooked rice. Wash and chop the vegetables.',
                                          'Cook the carrots and spinach in the olive oil; stir in the chickpeas and heat through.',
                                          'Serve with the rice, adjusting amounts of the shared components for each person.'],
                         'allergens': [], 'dietary_tags': ['vegan'], 'restriction_reviewed': False,
                         'ingredients': [{'name': name, 'quantity': grams, 'unit': 'g', 'state': state, 'food': foods[source],
                                          'component': component, 'grams_per_unit': None, 'conversion_note': ''}
                                         for name, grams, state, source, component in lines]})
