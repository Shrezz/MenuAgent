"""Calculation/evaluation tools for future candidates; no model or worker here."""
from application.domain.models import MEAL_TYPES
from application.domain.nutrition import calculate_portion, calculate_recipe, combine, fingerprint, portion_factors
from application.domain.recipes import ALLERGENS, NUTRIENTS, normalize_name, positive


def evaluate_menu(menu, recipes, members, inventory=(), settings=None, expected_slots=None):
    """A menu has version_id and meals: id/day/meal_type/recipe_id/recipe_revision/batch_multiplier/portions.

    Members are explicit dictionaries; portions include member_id and one quantity mode.
    Inventory quantities must be normalized grams plus canonical_name/state, or unknown.
    """
    settings = settings or {}
    expected = set(expected_slots if expected_slots is not None else ((day, meal) for day in range(7) for meal in MEAL_TYPES))
    issues, actual, families, slot_ids = [], [], set(), set()
    daily, needs = {}, {}
    member_map = {member['id']: member for member in members}

    def issue(code, message, severity='missing_data', slot_id=None):
        issues.append({'code': code, 'message': message, 'severity': severity, 'slot_id': slot_id})

    if not menu.get('version_id'):
        issue('missing_candidate_version', 'The candidate needs a version identifier.', 'required')
    if not members or len(member_map) != len(members):
        issue('invalid_household_members', 'Supply distinct household member profiles.', 'required')
    tolerance = positive(settings.get('target_tolerance', 0.1), 'Target tolerance', allow_zero=True)
    valid_inventory = []
    for row in inventory:
        try:
            grams = positive(row.get('grams'), 'Available stock grams', optional=True, allow_zero=True)
            valid_inventory.append(dict(row, grams=grams))
        except ValueError as error:
            issue('invalid_stock_quantity', str(error), 'required')

    for meal in menu.get('meals', []):
        slot_id = meal.get('id')
        if not slot_id or slot_id in slot_ids:
            issue('duplicate_slot_id', 'Meal slots need distinct identifiers.', 'required', slot_id)
        slot_ids.add(slot_id)
        actual.append((meal.get('day'), meal.get('meal_type')))
        recipe = recipes.get(meal.get('recipe_id'))
        if recipe is None:
            issue('missing_recipe', 'Choose a saved recipe for this slot.', slot_id=slot_id)
            continue
        if meal.get('recipe_revision') != recipe.get('revision'):
            issue('stale_recipe', 'The candidate must reference the exact saved recipe revision.', 'required', slot_id)
        family = recipe['dish_family']
        if family in families:
            issue('duplicate_dish', 'A finished dish repeats within the week.', 'required', slot_id)
        families.add(family)
        try:
            batch = positive(meal.get('batch_multiplier'), 'Prepared recipe multiplier')
        except ValueError as error:
            issue('invalid_batch', str(error), 'required', slot_id)
            continue
        computed = calculate_recipe(recipe, {line['component']: batch for line in recipe['ingredients']})
        for gap in computed['issues']:
            issue(gap['code'], f"{gap['ingredient']}: {gap['message']}", slot_id=slot_id)
        for need in computed['requirements']:
            key = (need['canonical_name'], need['state'])
            if key not in needs:
                needs[key] = need['grams']
            elif needs[key] is None or need['grams'] is None:
                needs[key] = None
            else:
                needs[key] += need['grams']
        used = {line['component']: 0.0 for line in recipe['ingredients']}
        assigned = set()
        for portion in meal.get('portions', []):
            member_id = portion.get('member_id')
            if member_id not in member_map or member_id in assigned:
                issue('invalid_member_portion', 'Portions must refer to distinct household members.', 'required', slot_id)
                continue
            assigned.add(member_id)
            try:
                factors = portion_factors(recipe, portion)
                if not any(factors.values()):
                    raise ValueError('At least one shared component must have a positive portion.')
                for name, factor in factors.items():
                    used[name] += factor
                totals = calculate_portion(recipe, portion)
                daily.setdefault((meal['day'], member_id), []).append(totals)
            except ValueError as error:
                issue('invalid_portion', str(error), 'required', slot_id)
        if any(value > batch + 1e-9 for value in used.values()):
            issue('portion_overallocation', 'Member portions exceed the prepared amount of a shared component.', 'required', slot_id)
        attending = meal.get('member_ids', list(member_map))
        if len(set(attending)) != len(attending) or any(member_id not in member_map for member_id in attending):
            issue('invalid_attendance', 'Attendance must contain distinct household members.', 'required', slot_id)
        if assigned != set(attending):
            issue('missing_portions', 'Enter portions only for all attending members; child portions are never invented.', slot_id=slot_id)
        for member_id in attending:
            member = member_map.get(member_id)
            if not member:
                continue
            restrictions = [normalize_name(value) for value in member.get('restrictions', '').split(',') if value.strip()]
            if restrictions and not recipe['restriction_reviewed']:
                issue('restriction_review_needed', 'Review ingredient allergens and dietary tags before checking this recipe.', slot_id=slot_id)
                continue
            aliases = {'dairy': 'milk', 'dairy free': 'milk', 'peanut': 'peanuts', 'gluten free': 'gluten', 'egg': 'eggs'}
            for restriction in restrictions:
                tag = aliases.get(restriction, restriction)
                if tag in ALLERGENS:
                    if tag in recipe['allergens'] or (tag == 'gluten' and 'wheat' in recipe['allergens']):
                        issue('allergen_conflict', f"{member['name']}: recipe contains {tag}.", 'required', slot_id)
                elif tag in ('vegetarian', 'vegan'):
                    if tag not in recipe['dietary_tags'] and not (tag == 'vegetarian' and 'vegan' in recipe['dietary_tags']):
                        issue('diet_conflict', f"{member['name']}: recipe is not marked {tag}.", 'required', slot_id)
                else:
                    issue('unrecognized_restriction', f"{member['name']}: restriction '{restriction}' needs explicit review.", slot_id=slot_id)
        day = meal.get('day')
        busy = day in settings.get('busy_day_indices', [])
        if busy and recipe.get('effort') not in ('assembly', 'simple'):
            issue('busy_day_effort', 'Prefer an easy recipe on this busier day; effort is involved or unknown.', 'recommendation', slot_id)
        if settings.get('cooking_effort') == 'assembly' and recipe.get('effort') != 'assembly':
            issue('effort_preference', 'This recipe requires more cooking than the assembly preference.', 'recommendation', slot_id)
    if len(actual) != len(set(actual)) or set(actual) != expected:
        issue('meal_coverage', 'The candidate does not fill each required meal slot exactly once.', 'required')
    totals = []
    for (day, member_id), results in sorted(daily.items()):
        aggregate = combine(results)
        member = member_map[member_id]
        targets = member.get('targets')
        differences = {key: aggregate['totals'][key] - targets[key] if aggregate['totals'][key] is not None else None for key in NUTRIENTS} if targets else None
        totals.append({'day': day, 'member_id': member_id, **aggregate, 'target_differences': differences})
        if targets and any(value is not None and abs(value) > targets[key] * tolerance for key, value in differences.items()):
            issue('target_deviation', f"{member['name']}: day {day + 1} differs from entered targets.", 'recommendation')
        if member.get('kind') == 'Child' and not targets:
            issue('child_balance_review', f"{member['name']}: balanced-food and age-appropriate serving review remains required; no numeric targets were inferred.", 'missing_data')
    shopping = []
    for (name, state), grams in sorted(needs.items()):
        matches = [row for row in valid_inventory if row.get('canonical_name') == name and row.get('state') == state]
        known = bool(matches) and all(row.get('grams') is not None for row in matches)
        available = sum(row['grams'] for row in matches) if known else None
        shortfall = max(0.0, grams - available) if grams is not None and available is not None else None
        shopping.append({'canonical_name': name, 'state': state, 'needed_g': grams, 'available_g': available, 'shortfall_g': shortfall})
        if available is None:
            issue('stock_unknown', f'{name} ({state}): confirm available grams or explicitly plan a purchase.')
        elif shortfall and not settings.get('allow_shopping', False):
            issue('stock_shortfall', f'{name} ({state}): {shortfall:g} g shortfall.', 'required')
        elif shortfall:
            issue('purchase_needed', f'{name} ({state}): purchase {shortfall:g} g.', 'recommendation')
    return {'candidate_version_id': menu.get('version_id'),
            'input_fingerprint': fingerprint(menu, recipes, members, inventory, settings),
            'issues': issues, 'daily_totals': totals, 'shopping': shopping,
            'ready': bool(menu.get('version_id')) and not any(row['severity'] in ('required', 'missing_data') for row in issues)}
