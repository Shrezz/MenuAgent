"""Live job progress and stored weekly candidates, separate from sample menus."""
from collections import Counter
from copy import deepcopy
from datetime import timedelta
import streamlit as st

from application.domain.models import MEAL_TYPES
from application.domain.recipes import STATES
from application.ui.components import records, service
from database.connection import StorageUnavailable


def render_planning(owner):
    st.subheader('Plan your household week')
    st.caption('One shared dish per meal, using saved recipes and new proposals when needed. The cook reviews new recipes; code checks nutrition, variety and stock needs.')
    with st.form('automatic-planning-options'):
        cuisine = st.selectbox('Cuisine focus', list(dict.fromkeys(['South Indian', *owner.cuisines, 'Everyday'])))
        left, right = st.columns(2)
        vegetarian = left.checkbox('Vegetarian recipes', value=True)
        web = right.checkbox('Find recipe sources online', value=True)
        new_recipes = left.checkbox('Suggest new recipes for review', value=True)
        shopping = right.checkbox('Allow a list of extra ingredients to buy', value=True)
        st.caption('Web discovery currently uses Dassana’s vegetarian recipe collection. New or imported recipes keep unknown nutrition until their source foods and quantities are reviewed.')
        with st.expander('Review stock preparation states'):
            st.caption('Choose raw, cooked or as sold for stock you want allocated precisely. Unconfirmed states and package-to-weight conversions stay unknown; shopping shows a conservative upper bound.')
            stock = [{'Ingredient':row['Item'],'Location':row['Location'],'Unit':row['Unit'],'State':None} for row in owner.inventory]
            if stock:
                edited = st.data_editor(stock, disabled=['Ingredient','Location','Unit'], hide_index=True, width='stretch',
                    column_config={'State':st.column_config.SelectboxColumn(options=STATES)},
                    key='planning-stock-states-' + str(owner.household_version))
            else:
                edited = []
                st.write('No confirmed stock yet. Add stock or review the proposed shopping list.')
        generate = st.form_submit_button('Generate automatic menu', type='primary')
    if generate:
        try:
            states = {'|'.join((row['Ingredient'].casefold(),row['Location'],row['Unit'])):row['State']
                      for row in records(edited) if row.get('State')}
            job_id = owner.menu_planner.start({'cuisine':cuisine,'vegetarian':vegetarian,'web':web,
                'new_recipes':new_recipes,'allow_shopping':shopping,'stock_states':states},force=True)
            st.session_state['planner-job-select'] = job_id
            st.success('Planning queued. Progress appears below; you can leave this page while it runs.')
        except (ValueError,StorageUnavailable) as error:
            st.error(str(error))
    render_job_progress()


@st.fragment(run_every='3s')
def render_job_progress():
    owner = service()  # Recheck editor access during fragment-only reruns too.
    try:
        planner = owner.menu_planner
        jobs = planner.jobs(owner.week_start)
        if not jobs:
            st.info('Generate a menu here, or confirm receipt purchases to start planning automatically.')
            return
        by_id = {job['id']:job for job in jobs}
        if st.session_state.get('planner-job-select') not in by_id:
            st.session_state.pop('planner-job-select',None)
        selected = st.selectbox('Planning job',list(by_id),key='planner-job-select',
            format_func=lambda value:f"{by_id[value]['created_at']:%b %d %H:%M} · {by_id[value]['status'].replace('_',' ')}")
        job = by_id[selected]
        st.write(f"**{job['status'].replace('_',' ').capitalize()}** · {job['progress']}")
        if job['status'] in ('queued','running'):
            st.caption('Progress refreshes automatically. A model request may take up to two minutes.')
            if st.button('Cancel planning',key='cancel-planning-' + selected):
                planner.repository.cancel(selected)
                st.rerun(scope='fragment')
        candidate = planner.repository.candidate(selected)
        if candidate is None:
            return
        current = owner.repository.read().version
        stale = current != job['input_version']
        if stale:
            st.warning('Household inputs have changed since this draft. Reload saved household data and generate a new menu.')
        elif candidate['report']['ready'] and job['status'] == 'draft_ready':
            st.success('This draft passed the implemented checks. Review portions, target differences and purchases. Finalization and ingredient reservations are a later milestone.')
        else:
            st.warning('This is a proposed menu with unresolved review items. Nutrition and dietary suitability are not yet fully verified.')
        render_candidate(candidate,owner.week_start)
    except (ValueError,StorageUnavailable) as error:
        st.error(str(error))


def render_candidate(candidate, week_start):
    menu, recipes, report = candidate['menu'], candidate['recipes'], candidate['report']
    members = {m['id']:m for m in candidate.get('members',[])}
    # Names come from the immutable snapshot, attached by the repository.
    tabs = st.tabs(['Automatic menu','Portions & nutrition','Prep & shopping','Recipe review','Sources & checks'])
    with tabs[0]:
        rows = []
        for day in range(7):
            row = {'Day':(week_start + timedelta(days=day)).strftime('%A')}
            for meal in menu['meals']:
                if meal['day'] == day:
                    row[meal['meal_type']] = recipes[meal['recipe_id']]['name']
            rows.append(row)
        st.dataframe(rows, hide_index=True, width='stretch')
        day = st.selectbox('See planned day',range(7),format_func=lambda n:(week_start + timedelta(days=n)).strftime('%A'),key='automatic-day-' + menu['version_id'])
        for meal in menu['meals']:
            if meal['day'] != day:
                continue
            recipe = recipes[meal['recipe_id']]
            with st.expander(f"{meal['meal_type']} · {recipe['name']}"):
                st.text(meal['reason'])
                st.write(f"Effort: {recipe.get('effort') or 'needs review'} · same dish for the household")
                st.caption('Prepared recipe multiplier reflects proposed adult/entered-target portions. Missing child portions must be reviewed before household quantities are complete.')
                st.write(f"Recipe batch multiplier: {meal['batch_multiplier']:.2f}")
                st.dataframe([{'Ingredient':line['name'],'Recipe quantity':line['quantity'],'Unit':line['unit'],
                               'Original source amount':line.get('source_ingredient_text','')} for line in recipe['ingredients']],hide_index=True,width='stretch')
                for step in recipe['instructions']:
                    st.text(step)
                if recipe.get('source_url'):
                    st.link_button('Open recipe source',recipe['source_url'])
    with tabs[1]:
        portion_rows = []
        for meal in menu['meals']:
            assigned = {p['member_id']:p for p in meal['portions']}
            for member_id,member in members.items():
                portion_rows.append({'Day':meal['day'] + 1,'Meal':meal['meal_type'],'Member':member['name'],
                    'Recipe':recipes[meal['recipe_id']]['name'],'Recipe servings':assigned.get(member_id,{}).get('servings'),
                    'Note':'Suggested serving, review for appetite and needs' if member_id in assigned else 'Serving pending human review'})
        st.dataframe(portion_rows,hide_index=True,width='stretch')
        daily = [{'Day':r['day'] + 1,'Member':members.get(r['member_id'],{}).get('name',r['member_id']),
                  **r['totals']} for r in report['daily_totals']]
        st.subheader('Calculated daily nutrition')
        st.caption('Blank values are unknown, never zero. Estimates come from ingredient source records and the proposed servings.')
        st.dataframe(daily,hide_index=True,width='stretch')
        st.subheader('Differences from entered targets')
        st.dataframe([{'Day':r['day'] + 1,'Member':members.get(r['member_id'],{}).get('name',r['member_id']),
                       **(r['target_differences'] or {})} for r in report['daily_totals']],hide_index=True,width='stretch')
    with tabs[2]:
        st.subheader('Ingredients for the whole week')
        st.caption('Check unknown stock before buying. When available grams are unknown, the needed grams are a conservative purchase upper bound, not an exact shortfall.')
        st.dataframe(report['shopping'],hide_index=True,width='stretch')
        prep = candidate.get('settings',{}).get('meal_prep')
        if prep == 'none':
            st.write('Your preference is no weekly meal prep. Plan preparation with each meal.')
        else:
            selected_ids = {meal['recipe_id'] for meal in menu['meals']}
            components = Counter(name for rid in selected_ids for name in {line['component'] for line in recipes[rid]['ingredients']} if name != 'Main dish')
            repeated = [name for name,count in components.items() if count > 1]
            st.write('Review opportunities to prepare shared components: ' + ', '.join(repeated) if repeated else 'No verified component batch schedule yet. Review recipe steps before combining preparation.')
        st.caption('Freezer amounts, storage guidance, reservations and cooking events remain pending; this draft does not consume stock.')
    with tabs[3]:
        pending = [recipes[rid] for rid in candidate['unreviewed_ids'] if rid in recipes]
        if not pending:
            st.write('This candidate uses saved recipes. Any missing source matches still appear in its checks.')
        for recipe in pending:
            with st.container(border=True):
                st.write(f"**{recipe['name']}** · {recipe['meal_type']}")
                st.caption(recipe['source_label'])
                if st.button('Review in recipe editor',key='review-planned-' + menu['version_id'] + recipe['id']):
                    st.session_state['recipe-new-document'] = deepcopy(recipe)
                    st.session_state['recipe-selected'] = 'new'
                    st.switch_page('application/ui/pages/recipes.py')
        st.caption('Save reviewed recipes, reload household data and generate again. The old candidate remains an immutable record.')
    with tabs[4]:
        st.dataframe(report['issues'],hide_index=True,width='stretch')
        for source in candidate.get('web_sources',[]):
            st.link_button(source['title'],source['url'])
        for note in candidate.get('web_notes',[]):
            st.caption(note)
        with st.expander('Agent tool steps'):
            st.dataframe(candidate.get('trace',[]),hide_index=True,width='stretch')
        st.caption(f"Model: {candidate['model']} · Candidate: {menu['version_id']} · The report applies to this saved version.")
