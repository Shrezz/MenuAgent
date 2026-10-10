"""Bounded planner: retrieve inputs, propose, calculate, evaluate and revise."""
from copy import deepcopy
from pathlib import Path
import re
from uuid import uuid4

from agent.state import AgentBudget
from agent.tools.calculations import validate_menu
from application.domain.models import MEAL_TYPES
from application.domain.recipes import clean_recipe, normalize_name, positive
from integrations.ollama_planner import OllamaPlanner
from integrations.ollama import ReceiptModelUnavailable
from integrations.recipe_web import RecipeWebClient, RecipeWebUnavailable, source_to_draft

RECIPE_SCHEMA = {'type':'object','additionalProperties':False,'required':['recipes'],'properties':{'recipes':{
    'type':'array','maxItems':7,'items':{'type':'object','additionalProperties':False,
    'required':['name','dish_family','cuisine','servings','effort','ingredients','instructions','source_url'],
    'properties':{'name':{'type':'string'},'dish_family':{'type':'string'},'cuisine':{'type':'string'},
        'servings':{'type':'number','minimum':0.1,'maximum':12},'effort':{'type':'string','enum':['assembly','simple','involved']},
        'source_url':{'type':'string'},'instructions':{'type':'array','maxItems':20,'items':{'type':'string'}},
        'ingredients':{'type':'array','maxItems':20,'items':{'type':'object','additionalProperties':False,
            'required':['name','quantity','unit','state','component'],'properties':{'name':{'type':'string'},
            'quantity':{'type':['number','null'],'minimum':0.001},'unit':{'type':'string','enum':['g','ml','each']},
            'state':{'type':'string','enum':['raw','cooked','as sold']},'component':{'type':'string'}}}}}}}}}
MENU_SCHEMA = {'type':'object','additionalProperties':False,'required':['meals'],'properties':{'meals':{
    'type':'array','minItems':28,'maxItems':28,'items':{'type':'object','additionalProperties':False,
    'required':['day','meal_type','recipe_id','portions','reason'],'properties':{
        'day':{'type':'integer','minimum':0,'maximum':6},'meal_type':{'type':'string','enum':list(MEAL_TYPES)},
        'recipe_id':{'type':'string'},'reason':{'type':'string'},'portions':{'type':'array','maxItems':20,'items':{
            'type':'object','additionalProperties':False,'required':['member_id','servings'],
            'properties':{'member_id':{'type':'string'},'servings':{'type':'number','minimum':0.1,'maximum':4}}}}}}}}}


def dish_identity(recipe):
    name = normalize_name(recipe['name'])
    for dish in ('bisi bele bath','lemon rice','tomato rice','curd rice','coconut rice','tamarind rice',
                 'idiyappam','uttapam','pesarattu','sundal','idli','dosa','upma','pongal','adai','puttu','appam'):
        if re.search(r'\b' + re.escape(dish) + r'\b',name):
            return dish
    return recipe['dish_family']


RECIPE_IDEAS = {
    'Breakfast':['Appam','Puttu','Idiyappam','Adai','Ven Pongal','Vegetable semiya','Ragi rotti'],
    'Lunch':['Lemon rice','Tomato rice','Coconut rice','Tamarind rice','Mint rice','Bisi bele bath','Vegetable biryani'],
    'Dinner':['Vegetable stew with chapati','Sambar rice','Vegetable kurma and rice','Avial with rice','Cabbage kootu and rice','Ragi mudde bowl','Vegetable uttapam'],
    'Snack':['Chickpea sundal','Roasted peanuts and fruit','Cucumber carrot salad','Steamed kozhukattai','Vegetable cutlet','Yogurt fruit bowl','Ragi porridge'],
}


def planning_settings(snapshot):
    settings = dict(snapshot['settings'], allow_shopping=snapshot['options'].get('allow_shopping', True))
    from datetime import date, timedelta
    week = date.fromisoformat(snapshot['week_start'])
    settings['busy_day_indices'] = [day for day in range(7) if (week + timedelta(days=day)).strftime('%A') in settings['busy_days']]
    return settings


def normalized_stock(snapshot, recipes):
    aliases = {}
    for recipe in recipes.values():
        for line in recipe['ingredients']:
            names = [line['name'], line['canonical_name'], *(line.get('food') or {}).get('aliases', [])]
            for name in names:
                aliases.setdefault(normalize_name(name), set()).add(line['canonical_name'])
    result = []
    states = snapshot['options'].get('stock_states', {})
    for row in snapshot['inventory']:
        name = normalize_name(row['Item'])
        matches = aliases.get(name, {name})
        canonical = next(iter(matches)) if len(matches) == 1 else name
        key = '|'.join((row['Item'].casefold(), row['Location'], row['Unit']))
        result.append({'canonical_name':canonical,'state':states.get(key),
                       'grams':0 if row['Status'] == 'Out' else row['Quantity'] if row['Unit'] == 'g' else None})
    return result


def assess_candidate(snapshot, menu, recipes, unreviewed_ids):
    settings = planning_settings(snapshot)
    members = deepcopy(snapshot['members'])
    if snapshot['options'].get('vegetarian', True):
        for member in members:
            member['restrictions'] = ','.join(filter(None, [member.get('restrictions',''), 'vegetarian']))
    report = validate_menu(menu, recipes, members, normalized_stock(snapshot, recipes), settings)
    identities = set()
    for meal in menu['meals']:
        recipe = recipes.get(meal['recipe_id'])
        if recipe:
            identity = dish_identity(recipe)
            if identity in identities:
                report['issues'].append({'code':'duplicate_finished_identity','severity':'required','slot_id':meal['id'], 'message':'A renamed variation of the same finished dish repeats in this week.'})
            identities.add(identity)
        if recipe and recipe['meal_type'] != meal['meal_type']:
            report['issues'].append({'code':'recipe_meal_type','severity':'required','slot_id':meal['id'], 'message':'Use a recipe assigned to this meal type.'})
        if recipe and meal['recipe_id'] in unreviewed_ids:
            report['issues'].append({'code':'new_recipe_review','severity':'missing_data','slot_id':meal['id'], 'message':f"Review the proposed recipe and nutrient matches: {recipe['name']}."})
        if recipe and snapshot['options'].get('vegetarian',True) and any(re.search(r'\b(chicken|beef|pork|fish|prawn|shrimp|mutton|meat|egg|eggs)\b', line['name'], re.I) for line in recipe['ingredients']):
            report['issues'].append({'code':'vegetarian_conflict','severity':'required','slot_id':meal['id'],'message':'An ingredient conflicts with the vegetarian planning preference.'})
    # Unknown stock cannot be allocated. With explicit shopping permission the
    # cook may buy the entire known requirement; we never pretend stock is zero.
    if settings['allow_shopping']:
        known_needs = {(r['canonical_name'],r['state']) for r in report['shopping'] if r['needed_g'] is not None}
        for issue in report['issues']:
            if issue['code'] == 'stock_unknown' and any(issue['message'].startswith(f'{name} ({state}):') for name,state in known_needs):
                issue['severity'] = 'recommendation'
                issue['message'] += ' Stock is not allocated; check it or buy up to the full listed requirement.'
    report['ready'] = not any(i['severity'] in ('required','missing_data') for i in report['issues'])
    return report


def clean_proposal(proposal, recipes, members):
    if not isinstance(proposal, dict) or set(proposal) != {'meals'} or not isinstance(proposal['meals'], list) or len(proposal['meals']) != 28:
        raise ValueError('The model must fill all 28 weekly meal slots.')
    member_map = {m['id']:m for m in members}
    meals = []
    for row in proposal['meals']:
        if not isinstance(row, dict) or set(row) != {'day','meal_type','recipe_id','portions','reason'}:
            raise ValueError('The model returned an invalid meal slot.')
        day, kind, recipe_id = row['day'], row['meal_type'], row['recipe_id']
        if isinstance(day,bool) or not isinstance(day,int) or day not in range(7) or kind not in MEAL_TYPES or not isinstance(recipe_id,str) or recipe_id not in recipes:
            raise ValueError('The model returned an unknown day, meal type or recipe.')
        if not isinstance(row['reason'],str) or len(row['reason']) > 1500 or not isinstance(row['portions'],list) or len(row['portions']) > 20:
            raise ValueError('The model returned invalid meal explanations or portions.')
        recipe = recipes[recipe_id]
        portions = []
        for p in row['portions']:
            if not isinstance(p,dict) or set(p) != {'member_id','servings'} or not isinstance(p['member_id'],str) or p['member_id'] not in member_map:
                raise ValueError('The model returned an unknown household member.')
            amount = positive(p['servings'],'Suggested servings')
            if not 0.1 <= amount <= 4:
                raise ValueError('Suggested servings must be between 0.1 and 4 recipe servings.')
            member = member_map[p['member_id']]
            if member['kind'] == 'Child' and not member.get('targets'):
                continue  # Do not silently create quantitative child portions.
            portions.append({'member_id':p['member_id'],'servings':amount})
        batch = sum(p['servings'] for p in portions) / recipe['servings']
        meals.append({'id':f'{day}-{kind}', 'day':day,'meal_type':kind,'recipe_id':recipe_id,
                      'recipe_revision':recipe['revision'],'batch_multiplier':max(batch,0.1),
                      'portions':portions,'reason':row['reason']})
    return {'version_id':str(uuid4()),'meals':meals}


def baseline_proposal(snapshot, recipes):
    """Build a complete candidate before asking the model to improve it."""
    from application.domain.nutrition import calculate_portion
    used, meals = set(), []
    busy = planning_settings(snapshot)['busy_day_indices']
    days = sorted(range(7),key=lambda day:(day not in busy,day))
    stock_names = {normalize_name(r['Item']) for r in snapshot['inventory'] if r['Status'] != 'Out'}
    fractions = {'Breakfast':0.25,'Lunch':0.30,'Dinner':0.30,'Snack':0.15}
    for day in days:
        for kind in MEAL_TYPES:
            choices = [r for r in recipes.values() if r['meal_type'] == kind and dish_identity(r) not in used]
            if not choices:
                raise ValueError(f'Not enough distinct {kind.lower()} recipes for a complete week.')
            def rank(recipe):
                easy = recipe.get('effort') in ('assembly','simple')
                on_hand = sum(normalize_name(line['name']) in stock_names for line in recipe['ingredients'])
                repeated = dish_identity(recipe) in snapshot.get('history_families',[])
                return (not easy if day in busy else False, repeated, -on_hand, recipe['name'])
            recipe = min(choices,key=rank)
            used.add(dish_identity(recipe))
            reference = calculate_portion(recipe,{'servings':1})['totals']['kcal']
            portions = []
            for member in snapshot['members']:
                if member['kind'] == 'Child' and not member.get('targets'):
                    continue
                amount = max(0.1,min(4,member['targets']['kcal'] * fractions[kind] / reference)) if member.get('targets') and reference else 1
                portions.append({'member_id':member['id'],'servings':amount})
            meals.append({'day':day,'meal_type':kind,'recipe_id':recipe['id'],'portions':portions,
                          'reason':'Initial selection favors distinct dishes, available ingredients and easy preparation on busy days; servings need review.'})
    return {'meals':sorted(meals,key=lambda row:(row['day'],MEAL_TYPES.index(row['meal_type'])))}


class PlanningAgent:
    def __init__(self, model=None, web=None, budget=None):
        self.model = model or OllamaPlanner()
        self.web = web or RecipeWebClient()
        self.budget = budget or AgentBudget()
        self.trace = []

    def run(self, snapshot, progress, save_candidate):
        def step(tool, message, kind='tool'):
            self.budget.step(kind)
            self.trace.append({'tool':tool,'message':message})
            progress(message)
        step('get_household_profile','Reading household preferences and confirmed stock')
        if not snapshot['members']:
            return 'needs_input', 'Add household members before planning.'
        recipes = deepcopy(snapshot['recipes'])
        unreviewed, sources, web_notes = [], [], []
        if snapshot['options'].get('new_recipes',True):
            for rid,recipe in snapshot.get('proposal_recipes',{}).items():
                if rid not in recipes:
                    recipes[rid] = deepcopy(recipe)
                    unreviewed.append(rid)
        if snapshot['options'].get('web',True):
            step('search_recipes','Looking for South Indian vegetarian recipes online','external')
            try:
                links = self.web.search('south indian', limit=12)
                for link in links[:3]:
                    step('import_recipe',f"Reading recipe source: {link['title'][:100]}",'external')
                    try:
                        sources.append(self.web.read(link['url']))
                    except RecipeWebUnavailable:
                        sources.append(dict(link, ingredients=[],instructions=[]))
                        web_notes.append('A recipe page could not be imported; its link needs manual review.')
            except RecipeWebUnavailable:
                web_notes.append('Web recipe search was unavailable. Suggestions use saved recipes and the local model.')
        for source in sources:
            if not source.get('ingredients') or not source.get('source_hash'):
                continue
            category = source.get('category','').casefold()
            kind = 'Breakfast' if 'breakfast' in category or 'brunch' in category else 'Snack' if 'snack' in category or 'dessert' in category else 'Lunch'
            recipe = source_to_draft(source, kind)
            recipe['dish_family'] = dish_identity(recipe)
            if recipe['dish_family'] not in {dish_identity(r) for r in recipes.values()}:
                recipes[recipe['id']] = recipe
                unreviewed.append(recipe['id'])
        for kind in MEAL_TYPES:
            families = {dish_identity(r) for r in recipes.values() if r['meal_type'] == kind}
            missing = max(0, 7 - len(families))
            if not missing:
                continue
            if not snapshot['options'].get('new_recipes',True):
                return 'needs_input', f'Add {missing} more distinct {kind.lower()} recipes or allow new recipe suggestions.'
            for recipe_attempt in range(2):
                missing = max(0, 7 - len({dish_identity(r) for r in recipes.values() if r['meal_type'] == kind}))
                if not missing:
                    break
                step('propose_recipes',f'Suggesting {missing} new {kind.lower()} recipes for review','model')
                schema = deepcopy(RECIPE_SCHEMA)
                schema['properties']['recipes']['minItems'] = missing
                schema['properties']['recipes']['maxItems'] = missing
                excluded = {dish_identity(r) for r in recipes.values()}
                ideas = [name for name in RECIPE_IDEAS[kind] if dish_identity({'name':name,'dish_family':normalize_name(name)}) not in excluded]
                proposal = self.model.propose(
                    f'Return EXACTLY {missing} NEW {kind.lower()} recipes in the recipes array. Suggested new dish names: {", ".join(ideas[:missing])}. Write a full practical recipe for each of those names, adapting to household ingredients. They must be different dishes from ALL excluded_dishes, including renamed variants. Do not reproduce imported recipes. Prioritize the requested cuisine, vegetarian preference, available ingredients and fewer steps. Lunch/dinner must be complete shared dishes, not only a condiment. Include oils and sauces. For novel proposals set source_url to an empty string; never attach another dish\'s source. Quantities are proposed recipe amounts, not verified weights. Do not invent nutrients. Respect all member restrictions and dislikes. Do not recommend overnight appliance cooking.',
                    {'meal_type':kind,'count':missing,'household':snapshot['members'],'stock':snapshot['inventory'],
                     'cuisine':snapshot['options'].get('cuisine','South Indian'),'settings':snapshot['settings'],
                     'vegetarian':snapshot['options'].get('vegetarian',True),
                     'excluded_dishes':sorted({dish_identity(r) for r in recipes.values()}),
                     'required_output_count':missing}, schema, timeout=self.budget.remaining())
                raw_recipes = proposal.get('recipes')
                if not isinstance(raw_recipes,list) or len(raw_recipes) > 7:
                    raise ValueError('The model returned an invalid recipe collection.')
                for raw in raw_recipes:
                    if not isinstance(raw,dict) or not isinstance(raw.get('ingredients'),list) or len(raw['ingredients']) > 20 or len(raw.get('instructions',[])) > 20:
                        raise ValueError('The model returned an invalid recipe suggestion.')
                    if raw.get('source_url'):
                        raise ValueError('A novel model proposal must not claim a web source.')
                    recipe = clean_recipe(dict(raw, id=str(uuid4()), meal_type=kind, revision=0,
                        source_label='AI recipe proposal; review quantities, method, source matches and dietary details',
                        restriction_reviewed=False, allergens=[], dietary_tags=[],
                        ingredients=[dict(line, food=None, grams_per_unit=None, conversion_note='') for line in raw['ingredients']]))
                    recipe['dish_family'] = normalize_name(recipe['name'])
                    recipe['dish_family'] = dish_identity(recipe)
                    if recipe['dish_family'] not in {dish_identity(r) for r in recipes.values()}:
                        recipes[recipe['id']] = recipe
                        unreviewed.append(recipe['id'])
            if len({dish_identity(r) for r in recipes.values() if r['meal_type'] == kind}) < 7:
                menu = {'version_id':str(uuid4()),'meals':[]}
                save_candidate({'menu':menu,'recipes':recipes,'unreviewed_ids':unreviewed,
                    'report':assess_candidate(snapshot,menu,recipes,unreviewed), 'trace':deepcopy(self.trace),
                    'model':self.model.model,'web_sources':sources,'web_notes':list(web_notes)})
                return 'needs_input', f'The recipe suggestions did not supply seven distinct {kind.lower()} dishes. Add recipes or retry.'
        catalog = []
        for recipe in recipes.values():
            from application.domain.nutrition import calculate_portion
            catalog.append({k:recipe[k] for k in ('id','name','dish_family','meal_type','cuisine','servings','effort')})
            catalog[-1]['ingredients'] = [{k:line[k] for k in ('name','quantity','unit','state','component')} for line in recipe['ingredients']]
            catalog[-1]['reference_serving_nutrition'] = calculate_portion(recipe, {'servings':1})['totals']
        prior, report, last, best, best_score = None, None, None, None, None
        def quality(assessment):
            target_error = 0
            profiles = {m['id']:m for m in snapshot['members']}
            for row in assessment['daily_totals']:
                targets = profiles[row['member_id']].get('targets')
                if targets and row['target_differences']:
                    target_error += sum(abs(value) / targets[key] for key,value in row['target_differences'].items() if value is not None)
            return (sum(i['severity'] == 'required' for i in assessment['issues']),
                    sum(i['severity'] == 'missing_data' for i in assessment['issues']), target_error,
                    sum(i['code'] in ('busy_day_effort','effort_preference') for i in assessment['issues']))
        step('build_initial_candidate','Building a complete week from the recipe pool')
        prior = clean_proposal(baseline_proposal(snapshot,recipes),recipes,snapshot['members'])
        report = assess_candidate(snapshot,prior,recipes,unreviewed)
        step('save_weekly_menu','Saving the initial week and its calculated checks')
        last = save_candidate({'menu':prior,'recipes':recipes,'unreviewed_ids':unreviewed,'report':report,
            'trace':deepcopy(self.trace),'model':self.model.model,'web_sources':sources,'web_notes':list(web_notes)})
        best, best_score = deepcopy(last), quality(last['report'])
        instructions = Path(__file__).with_name('prompts').joinpath('planner.md').read_text()
        for revision in range(self.budget.max_revisions):
            step('propose_menu',f'Choosing shared meals and portions · attempt {revision + 1}','model')
            try:
                proposal = self.model.propose(instructions + '\nReturn 28 slots, four meal types each day 0 through 6. Use only supplied recipe IDs and match their meal_type. Exactly one shared recipe per slot. Include a serving for each adult and for children only with entered numeric targets; leave other child portions for human review. A serving is relative to the saved recipe yield. Prefer new finished dishes across the week and avoid recent history; favor easy meals on busy days. Revise any required validation issues using the evaluator feedback. The initial week is already complete: improve it without removing or repeating slots.',
                    {'snapshot':{k:v for k,v in snapshot.items() if k not in ('recipes','proposal_recipes')}, 'recipes':catalog,
                     'previous_menu':prior,'evaluation':report}, MENU_SCHEMA, timeout=self.budget.remaining())
            except ReceiptModelUnavailable:
                web_notes.append('The local model could not finish a menu revision. The initial calculated candidate was retained; review its checks or try another installed model.')
                break
            try:
                menu = clean_proposal(proposal, recipes, snapshot['members'])
            except (ValueError,TypeError,KeyError,OverflowError):
                report = {'issues':[{'code':'invalid_model_menu','severity':'required','message':'Return all required slots with known recipe/member IDs and valid portions.'}]}
                continue
            step('calculate_nutrition_and_validate','Calculating whole-week nutrition, stock needs and variety')
            report = assess_candidate(snapshot, menu, recipes, unreviewed)
            step('save_weekly_menu','Saving this candidate with its validation report')
            last = save_candidate({'menu':menu,'recipes':recipes,'unreviewed_ids':unreviewed,
                'report':report,'trace':deepcopy(self.trace),'model':self.model.model,'web_sources':sources,'web_notes':list(web_notes)})
            report, prior = last['report'], menu
            score = quality(report)
            if best_score is None or score < best_score:
                best, best_score = deepcopy(last), score
            if report['ready'] and not any(i['code'] == 'target_deviation' for i in report['issues']):
                return 'draft_ready', 'Seven-day draft checked. Review portions, target differences and proposed shopping.'
            # Missing source matches/child review cannot be fixed by more guesses.
            if not report['ready'] and not any(i['severity'] == 'required' for i in report['issues']):
                break
        if best and last and (quality(last['report']) > best_score or web_notes != last.get('web_notes',[])):
            best['menu']['version_id'] = str(uuid4())
            step('save_best_candidate','Keeping the best checked candidate from the bounded revisions')
            best['trace'] = deepcopy(self.trace)
            best['web_notes'] = web_notes
            last = save_candidate(best)
        if last and last['report']['ready']:
            return 'draft_ready', 'Seven-day draft checked. Remaining target differences and shopping needs are visible.'
        if last:
            return 'needs_input', 'Draft saved with review issues. Review proposed recipes, portions and nutrition matches before using it as a checked plan.'
        return 'needs_input', 'The model could not produce a valid weekly candidate within the revision limit. Retry or choose another installed model.'
