from copy import deepcopy
from uuid import uuid4
import pandas as pd
import streamlit as st

from application.domain.models import MEAL_TYPES
from application.domain.nutrition import calculate_portion, calculate_recipe
from application.domain.recipes import ALLERGENS, DIETS, EFFORTS, NUTRIENTS, STATES
from application.services.recipe_examples import example_recipe
from application.ui.components import page_heading, records, service
from database.connection import StorageUnavailable
from integrations.usda import USDAClient, USDAUnavailable, match_candidates

owner = service()
library = owner.recipe_library
page_heading('Familiar favorites, fresh ideas', 'Recipes', 'Save quantities and preparation steps, review source foods, and calculate household portions.')
scope = 'in your household' if owner.persistent else 'for this session'
st.caption('Saved recipes have their own ingredient and nutrition records. The weekly menu is still a separate sample preview.')
collection, editor, sources = st.tabs(['Saved recipes & portions', 'Add or edit recipe', 'Source foods'])


def show_totals(result):
    columns = st.columns(4)
    for column, key, label, unit in zip(columns, NUTRIENTS, ['Calories', 'Protein', 'Carbs', 'Fat'], ['kcal', 'g', 'g', 'g']):
        value = result['totals'][key]
        column.metric(label, f'{value:.1f} {unit}' if value is not None else 'Incomplete')
    if not result['complete']:
        st.warning('Some quantities or nutrients are missing. These are not complete nutrition totals.')
        st.dataframe([{'Nutrient': key, 'Known subtotal only': result['known_subtotals'][key]} for key in NUTRIENTS], hide_index=True)
    for issue in result['issues']:
        st.caption(f"{issue['ingredient']}: {issue['message']}")


with editor:
    choices = ['new'] + list(library.recipes)
    selected = st.selectbox('Recipe to edit', choices, format_func=lambda value: 'New recipe' if value == 'new' else library.recipes[value]['name'], key='recipe-selected')
    if selected == 'new':
        if 'recipe-new-document' not in st.session_state:
            st.session_state['recipe-new-document'] = {'id': str(uuid4())}
        if st.button('Load example into editor'):
            st.session_state['recipe-new-document'] = example_recipe()
            st.rerun()
        if st.button('Start another recipe'):
            st.session_state['recipe-new-document'] = {'id': str(uuid4())}
            st.rerun()
        document = st.session_state['recipe-new-document']
    else:
        document = library.recipes[selected]
    prefix = f"recipe-form-{document['id']}-{document.get('revision', 0)}"
    original_lines = document.get('ingredients', [])
    # Keep historical sources selectable alongside newly retrieved source records.
    def food_key(food):
        return f"{food['id']}:{food['state']}:{food['source_hash']}"
    source_snapshots = {food_key(food): food for food in library.foods.values()}
    source_snapshots.update({food_key(line['food']): line['food'] for line in original_lines if line.get('food')})
    labels = {identifier: f"{food['name']} · {food['state']} · {food['id']} · {food['source_hash'][:8]}"
              for identifier, food in source_snapshots.items()}
    source_ids = {label: identifier for identifier, label in labels.items()}
    rows = [{'Ingredient': line['name'], 'Quantity': line['quantity'], 'Unit': line['unit'], 'State': line['state'],
             'Source food': labels.get(food_key(line['food'])) if line.get('food') else None,
             'Shared component': line['component'], 'Grams per unit': line.get('grams_per_unit'), 'Conversion note': line.get('conversion_note', '')}
            for line in original_lines]
    if not rows:
        rows = [{'Ingredient': '', 'Quantity': None, 'Unit': 'g', 'State': 'raw', 'Source food': None,
                 'Shared component': 'Main dish', 'Grams per unit': None, 'Conversion note': ''}]
    frame = pd.DataFrame(rows).astype({'Ingredient': 'string', 'Quantity': 'float64', 'Unit': 'string', 'State': 'string',
                                      'Source food': 'string', 'Shared component': 'string', 'Grams per unit': 'float64', 'Conversion note': 'string'})
    with st.form(prefix):
        name = st.text_input('Recipe name', value=document.get('name', ''), key=prefix+'-name')
        family = st.text_input('Finished-dish identity', value=document.get('dish_family', ''), help='Use the same identity for variations of the same finished dish, so renaming does not hide repetition.')
        left, middle, right = st.columns(3)
        meal_type = left.selectbox('Recipe meal type', MEAL_TYPES, index=MEAL_TYPES.index(document.get('meal_type', 'Dinner')))
        cuisine = middle.text_input('Recipe cuisine', value=document.get('cuisine', 'Everyday'))
        servings = right.number_input('Recipe servings', min_value=0.1, value=float(document.get('servings', 4)), step=0.5)
        left, right = st.columns(2)
        yield_g = left.number_input('Finished yield (g, optional)', min_value=1.0, value=document.get('cooked_yield_g'), help='Needed only when portions are entered as finished grams.')
        yield_note = right.text_input('Yield measurement or assumption', value=document.get('yield_note', ''))
        st.caption('Include oils, sauces and seasonings. Choose a source food that matches the ingredient and its preparation state. Leave uncertain amounts or source matches blank.')
        edited = st.data_editor(frame, hide_index=True, num_rows='dynamic', width='stretch', key=prefix+'-ingredients', column_config={
            'Ingredient': st.column_config.TextColumn(required=True),
            'Quantity': st.column_config.NumberColumn(min_value=0.0),
            'Unit': st.column_config.SelectboxColumn(options=['g', 'ml', 'each']),
            'State': st.column_config.SelectboxColumn(options=STATES),
            'Source food': st.column_config.SelectboxColumn(options=list(source_ids)),
            'Grams per unit': st.column_config.NumberColumn(min_value=0.0),
        })
        st.caption('For ml or each, enter ingredient-specific grams per unit with a measurement/source note. Grams need no conversion.')
        instructions = st.text_area('Preparation steps (one per line)', value='\n'.join(document.get('instructions', [])))
        effort = st.selectbox('Recipe effort', EFFORTS, index=EFFORTS.index(document['effort']) if document.get('effort') else None,
                              help='Judge steps, chopping and attention rather than inferring effort from minutes.')
        active_minutes = st.number_input('Estimated hands-on minutes (optional)', min_value=0.0, value=document.get('active_minutes'))
        equipment = st.text_input('Equipment (comma separated)', value=', '.join(document.get('equipment', [])))
        source_label = st.text_input('Recipe source', value=document.get('source_label', 'Household recipe'))
        source_url = st.text_input('Recipe source URL (optional)', value=document.get('source_url', ''))
        allergens = st.multiselect('Allergens present in ingredients', ALLERGENS, default=document.get('allergens', []))
        diets = st.multiselect('Reviewed dietary tags', DIETS, default=document.get('dietary_tags', []))
        reviewed = st.checkbox('Ingredient allergens and dietary tags reviewed', value=document.get('restriction_reviewed', False))
        saved = st.form_submit_button('Save recipe', type='primary')
    if saved:
        try:
            lines = []
            for row in records(edited):
                if not row.get('Ingredient') and row.get('Quantity') is None:
                    continue
                source_id = source_ids.get(row.get('Source food'))
                food = source_snapshots.get(source_id) if source_id else None
                lines.append({'name': row.get('Ingredient'), 'quantity': row.get('Quantity'), 'unit': row.get('Unit') or 'g',
                              'state': row.get('State') or 'raw', 'food': deepcopy(food), 'component': row.get('Shared component') or 'Main dish',
                              'grams_per_unit': row.get('Grams per unit'), 'conversion_note': row.get('Conversion note') or ''})
            result = library.save({'id': document['id'], 'name': name, 'dish_family': family, 'meal_type': meal_type,
                                   'cuisine': cuisine, 'servings': servings, 'cooked_yield_g': yield_g, 'yield_note': yield_note,
                                   'ingredients': lines, 'instructions': instructions.splitlines(), 'effort': effort,
                                   'active_minutes': active_minutes, 'equipment': [item.strip() for item in equipment.split(',') if item.strip()],
                                   'source_label': source_label, 'source_url': source_url, 'allergens': allergens,
                                   'dietary_tags': diets, 'restriction_reviewed': reviewed})
            st.success(f"{result['name']} saved {scope} · revision {result['revision']}.")
        except (ValueError, StorageUnavailable) as error:
            st.error(str(error))

with collection:
    left, middle, right = st.columns([2, 1, 1])
    query = left.text_input('Search saved recipes', placeholder='Ingredient or dish name')
    selected_meal = middle.selectbox('Meal type', ['All', *MEAL_TYPES])
    selected_cuisine = right.selectbox('Cuisine', ['All', *sorted({recipe['cuisine'] for recipe in library.recipes.values()})])
    filtered = [recipe for recipe in library.recipes.values() if (selected_meal == 'All' or recipe['meal_type'] == selected_meal)
                and (selected_cuisine == 'All' or recipe['cuisine'] == selected_cuisine)
                and (not query or query.casefold() in ' '.join([recipe['name'], *(line['name'] for line in recipe['ingredients'])]).casefold())]
    st.caption(f'{len(filtered)} saved recipes · {scope}')
    if not filtered:
        st.info('Use Add or edit recipe to create your first recipe, or load the example into the editor.')
    for recipe in filtered:
        with st.expander(f"{recipe['name']} · {recipe['meal_type']} · revision {recipe['revision']}"):
            st.caption(f"{recipe['cuisine']} · {recipe['servings']:g} reference servings · {recipe.get('effort') or 'effort not entered'}")
            if recipe['source_url']:
                st.link_button(recipe['source_label'], recipe['source_url'])
            else:
                st.caption(recipe['source_label'])
            st.dataframe([{'Ingredient': line['name'], 'Quantity': line['quantity'], 'Unit': line['unit'], 'State': line['state'],
                           'Component': line['component'], 'Source match': line['food']['name'] if line.get('food') else 'Unmatched'} for line in recipe['ingredients']], hide_index=True)
            for index, step in enumerate(recipe['instructions'], 1):
                st.write(f'{index}. {step}')
            st.write('**Whole recipe nutrition estimate**')
            show_totals(calculate_recipe(recipe))
            st.write('**Portion calculator**')
            mode = st.radio('Portion measurement', ['Reference servings', 'Finished grams', 'Shared component fractions'], key=f"portion-mode-{recipe['id']}")
            try:
                if mode == 'Finished grams':
                    grams = st.number_input('Portion weight (g)', min_value=1.0, value=100.0, key=f"portion-g-{recipe['id']}")
                    portion = {'grams': grams}
                elif mode == 'Shared component fractions':
                    st.caption('Enter the fraction of each entire recipe component for one person. 0.25 means one quarter.')
                    portion = {'component_fractions': {component: st.number_input(component, min_value=0.0, max_value=1.0, value=min(1.0, 1.0 / recipe['servings']), key=f"portion-component-{recipe['id']}-{component}") for component in dict.fromkeys(line['component'] for line in recipe['ingredients'])}}
                else:
                    count = st.number_input('Reference servings for this portion', min_value=0.1, value=1.0, step=0.25, key=f"portion-count-{recipe['id']}")
                    portion = {'servings': count}
                portion_result = calculate_portion(recipe, portion)
                show_totals(portion_result)
                if owner.members:
                    by_id = {member.id: member for member in owner.members}
                    member_id = st.selectbox('Compare with household member', list(by_id), format_func=lambda value: by_id[value].name, key=f"recipe-member-{recipe['id']}")
                    member = by_id[member_id]
                    if member.targets:
                        st.caption('This is one portion, not a full day. Targets are the member’s entered daily goals.')
                        st.dataframe([{'Nutrient': key, 'Portion': portion_result['totals'][key], 'Entered daily target': member.targets[key]} for key in NUTRIENTS], hide_index=True)
                    else:
                        st.caption('No numeric targets entered. This calculator does not invent child targets or recommended child portions.')
            except ValueError as error:
                st.info(str(error))
            with st.expander('Nutrition sources and saved revisions'):
                for food in {line['food']['id']: line['food'] for line in recipe['ingredients'] if line.get('food')}.values():
                    st.link_button(food['name'], food['source_url'])
                    st.caption(f"{food['state']} · retrieved {food['retrieved_at']} · source hash {food['source_hash'][:12]}")
                st.caption(f"{len(library.revisions(recipe['id']))} immutable recipe revisions saved.")

with sources:
    st.caption('Nine bundled USDA food records are available offline. Matches require review; aliases may return several raw/cooked candidates.')
    ingredient = st.text_input('Ingredient to match', placeholder='chickpeas')
    state = st.selectbox('Matching preparation state', ['Any', *STATES])
    candidates = match_candidates(library.foods, ingredient, None if state == 'Any' else state) if ingredient else list(library.foods.values())
    st.dataframe([{'Source food': food['name'], 'State': food['state'], 'FDC ID': food.get('fdc_id'), **food['nutrients'], 'Source': food['source_url']} for food in candidates], hide_index=True, width='stretch')
    with st.expander('Find more USDA source foods'):
        search = st.text_input('USDA food search')
        if st.button('Search USDA'):
            try:
                st.session_state['recipe-usda-candidates'] = USDAClient().search(search)
            except USDAUnavailable as error:
                st.error(str(error))
        found = st.session_state.get('recipe-usda-candidates', [])
        if found:
            selected_food = st.selectbox('Review USDA candidate', list(range(len(found))), format_func=lambda value: f"{found[value]['name']} · {found[value]['fdc_id']}")
            source_state = st.selectbox('Confirmed preparation state', STATES)
            aliases = st.text_input('Ingredient aliases (comma separated)')
            if st.button('Save reviewed source food'):
                try:
                    food = USDAClient().detail(found[selected_food]['fdc_id'], source_state, [value.strip() for value in aliases.split(',') if value.strip()])
                    library.save_food(food)
                    st.success(f"Source food saved {scope}. It will be available in the recipe editor on the next page refresh.")
                except (ValueError, StorageUnavailable) as error:
                    st.error(str(error))
    st.caption('Recipe web discovery and automatic recipe extraction arrive in milestone 4. This editor saves recipes you enter.')
