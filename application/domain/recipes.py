"""Structured recipe documents with explicit quantities and source snapshots."""
from copy import deepcopy
from math import isfinite
import re
from urllib.parse import urlparse
from uuid import UUID, uuid4

from application.domain.models import MEAL_TYPES

NUTRIENTS = ('kcal', 'protein', 'carbs', 'fat')
STATES = ('raw', 'cooked', 'as sold')
EFFORTS = ('assembly', 'simple', 'involved')
ALLERGENS = ('milk', 'eggs', 'fish', 'shellfish', 'tree nuts', 'peanuts', 'wheat', 'soy', 'sesame', 'gluten')
DIETS = ('vegetarian', 'vegan')


def normalize_name(value):
    return ' '.join(re.sub(r'[^\w\s]', ' ', str(value).casefold()).split())


def positive(value, label, optional=False, allow_zero=False):
    if optional and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value) or value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f'{label} must be a finite {"non-negative" if allow_zero else "positive"} number.')
    return float(value)


def text(value, label, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise ValueError(f'Enter {label} of up to {limit} characters.')
    return value.strip()


def clean_food(food):
    result = deepcopy(food)
    result['id'] = text(food.get('id'), 'source food identifier')
    result['name'] = text(food.get('name'), 'source food name', 500)
    if food.get('state') not in STATES:
        raise ValueError('Choose a preparation state for the source food.')
    for key in ('source_url', 'retrieved_at', 'source_hash'):
        result[key] = text(food.get(key), key, 1000)
    source = urlparse(result['source_url'])
    if source.scheme != 'https' or source.hostname != 'fdc.nal.usda.gov':
        raise ValueError('A USDA FoodData Central source link is required.')
    if set(food.get('nutrients', {})) != set(NUTRIENTS):
        raise ValueError('Food records must expose all four nutrients, including missing values.')
    result['nutrients'] = {key: positive(food['nutrients'][key], key, optional=True, allow_zero=True) for key in NUTRIENTS}
    result['aliases'] = list(dict.fromkeys(normalize_name(alias) for alias in food.get('aliases', []) if normalize_name(alias)))
    result['canonical_name'] = normalize_name(food.get('canonical_name') or (result['aliases'][0] if result['aliases'] else result['name']))
    return result


def clean_recipe(document):
    d = deepcopy(document)
    d['id'] = str(UUID(d.get('id') or str(uuid4())))
    d['name'] = text(d.get('name'), 'recipe name')
    d['dish_family'] = normalize_name(d.get('dish_family') or d['name'])
    if not d['dish_family']:
        raise ValueError('Enter a finished-dish identity.')
    if d.get('meal_type') not in MEAL_TYPES:
        raise ValueError('Choose a meal type.')
    d['cuisine'] = text(d.get('cuisine'), 'cuisine')
    d['servings'] = positive(d.get('servings'), 'Recipe servings')
    d['cooked_yield_g'] = positive(d.get('cooked_yield_g'), 'Finished yield', optional=True)
    d['yield_note'] = str(d.get('yield_note') or '').strip()
    if d['cooked_yield_g'] is not None and not d['yield_note']:
        raise ValueError('Describe how the finished yield was measured or estimated.')
    d['source_label'] = text(d.get('source_label') or 'Household recipe', 'recipe source')
    d['source_url'] = str(d.get('source_url') or '').strip()
    if d['source_url'] and (urlparse(d['source_url']).scheme not in ('http', 'https') or not urlparse(d['source_url']).hostname):
        raise ValueError('Enter an HTTP or HTTPS recipe source URL.')
    if d.get('effort') is not None and d['effort'] not in EFFORTS:
        raise ValueError('Choose assembly, simple or involved effort.')
    d['active_minutes'] = positive(d.get('active_minutes'), 'Estimated active minutes', optional=True, allow_zero=True)
    d['equipment'] = [text(item, 'equipment') for item in d.get('equipment', [])]
    d['instructions'] = [text(item, 'instruction', 2000) for item in d.get('instructions', []) if str(item).strip()]
    if not d['instructions']:
        raise ValueError('Add at least one preparation step.')
    if len(d['instructions']) > 100 or len(d.get('ingredients', [])) > 100:
        raise ValueError('Recipes support up to 100 steps and ingredients.')
    d['restriction_reviewed'] = d.get('restriction_reviewed', False)
    if not isinstance(d['restriction_reviewed'], bool):
        raise ValueError('Restriction review must be true or false.')
    for key, options in (('allergens', ALLERGENS), ('dietary_tags', DIETS)):
        values = d.get(key, [])
        if any(value not in options for value in values) or len(set(values)) != len(values):
            raise ValueError(f'Choose supported {key}.')
        d[key] = list(values)
    ingredients = []
    for line in d.get('ingredients', []):
        item = deepcopy(line)
        item['name'] = text(item.get('name'), 'ingredient')
        item['canonical_name'] = normalize_name(item['name'])
        item['quantity'] = positive(item.get('quantity'), 'Ingredient quantity', optional=True)
        if item.get('unit') not in ('g', 'ml', 'each') or item.get('state') not in STATES:
            raise ValueError('Choose a supported ingredient unit and preparation state.')
        item['component'] = text(item.get('component') or 'Main dish', 'shared component')
        item['grams_per_unit'] = positive(item.get('grams_per_unit'), 'Grams per unit', optional=True)
        item['conversion_note'] = str(item.get('conversion_note') or '').strip()
        if item['unit'] != 'g' and item['grams_per_unit'] is not None and not item['conversion_note']:
            raise ValueError('A volume/count conversion needs a reviewed source or measurement note.')
        item['food'] = clean_food(item['food']) if item.get('food') else None
        if item['food']:
            item['canonical_name'] = item['food']['canonical_name']
        ingredients.append(item)
    if not ingredients:
        raise ValueError('Add at least one ingredient.')
    d['ingredients'] = ingredients
    return d
