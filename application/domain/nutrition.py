"""Deterministic arithmetic: unknown nutrients are never replaced with zero."""
from hashlib import sha256
import json

from application.domain.recipes import NUTRIENTS, positive


def grams_for(line):
    quantity = line.get('quantity')
    if quantity is None:
        return None
    if line['unit'] == 'g':
        return quantity
    conversion = line.get('grams_per_unit')
    return quantity * conversion if conversion is not None and line.get('conversion_note') else None


def combine(results):
    return {
        'totals': {key: sum(result['totals'][key] for result in results) if all(result['totals'][key] is not None for result in results) else None for key in NUTRIENTS},
        'known_subtotals': {key: sum(result['known_subtotals'][key] for result in results) for key in NUTRIENTS},
    }


def calculate_recipe(recipe, component_factors=None):
    """Factors refer to fractions of the entire recipe's named components."""
    factors = component_factors or {line['component']: 1.0 for line in recipe['ingredients']}
    components, issues, requirements = {}, [], []
    for index, line in enumerate(recipe['ingredients']):
        factor = factors.get(line['component'], 0.0)
        positive(factor, 'Component factor', allow_zero=True)
        if factor == 0:
            continue
        grams, food = grams_for(line), line.get('food')
        usable = food is not None and food['state'] == line['state'] and grams is not None
        if grams is None:
            issues.append({'code': 'unknown_quantity', 'ingredient': line['name'], 'line': index,
                           'message': 'Enter a quantity in grams or a reviewed volume/count conversion.'})
        if food is None:
            issues.append({'code': 'unmatched_food', 'ingredient': line['name'], 'line': index, 'message': 'Review a source-food match.'})
        elif food['state'] != line['state']:
            issues.append({'code': 'preparation_mismatch', 'ingredient': line['name'], 'line': index, 'message': 'The recipe and source food have different preparation states.'})
        totals = {key: grams * factor / 100 * food['nutrients'][key] if usable and food['nutrients'][key] is not None else None for key in NUTRIENTS}
        if usable and any(value is None for value in totals.values()):
            issues.append({'code': 'missing_nutrients', 'ingredient': line['name'], 'line': index, 'message': 'The source food is missing one or more nutrients.'})
        result = {'totals': totals, 'known_subtotals': {key: value if value is not None else 0.0 for key, value in totals.items()}}
        components.setdefault(line['component'], []).append(result)
        requirements.append({'canonical_name': line['canonical_name'], 'state': line['state'], 'grams': grams * factor if grams is not None else None})
    by_component = {name: combine(rows) for name, rows in components.items()}
    result = combine(list(by_component.values()))
    result.update(components=by_component, issues=issues, requirements=requirements,
                  complete=all(value is not None for value in result['totals'].values()),
                  sources=[line['food'] for line in recipe['ingredients'] if line.get('food')])
    return result


def portion_factors(recipe, portion):
    modes = [key for key in ('servings', 'grams', 'component_fractions') if portion.get(key) is not None]
    if len(modes) != 1:
        raise ValueError('Enter exactly one portion mode: servings, finished grams, or component fractions.')
    components = {line['component'] for line in recipe['ingredients']}
    if modes[0] == 'component_fractions':
        factors = portion['component_fractions']
        if not isinstance(factors, dict) or not factors or any(key not in components for key in factors):
            raise ValueError('Portions must refer to existing shared components.')
        return {key: positive(factors.get(key, 0), 'Component fraction', allow_zero=True) for key in components}
    if modes[0] == 'grams':
        if recipe.get('cooked_yield_g') is None or not recipe.get('yield_note'):
            raise ValueError('A measured or explained finished yield is required for gram portions.')
        fraction = positive(portion['grams'], 'Finished serving grams') / recipe['cooked_yield_g']
    else:
        fraction = positive(portion['servings'], 'Portion servings') / recipe['servings']
    return {key: fraction for key in components}


def calculate_portion(recipe, portion):
    return calculate_recipe(recipe, portion_factors(recipe, portion))


def fingerprint(menu, recipes, members, inventory, settings):
    payload = {'menu': menu, 'recipes': recipes, 'members': members, 'inventory': inventory, 'settings': settings}
    return sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
