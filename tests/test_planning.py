"""Synthetic recipe identities verify contracts; these are not recommended menus."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from agent.runtime import PlanningAgent, RECIPE_SCHEMA, assess_candidate, clean_proposal
from agent.state import AgentBudget, PlanningBudgetExceeded
from application.domain.models import MEAL_TYPES
from application.services.menus import clean_options
from application.services.recipe_examples import example_recipe
from integrations.recipe_web import RecipeWebUnavailable, checked_url, parse_recipe_page, source_to_draft
from integrations.ollama import ReceiptModelUnavailable
from integrations.ollama_planner import OllamaPlanner


def planning_fixture(member_id='adult'):
    example = dict(example_recipe(),revision=1)
    recipes = {}
    for kind in MEAL_TYPES:
        for day in range(7):
            recipe = dict(deepcopy(example),id=str(uuid4()),name=f'Fixture {kind} {day}',dish_family=f'fixture-{kind}-{day}',meal_type=kind)
            recipes[recipe['id']] = recipe
    stock, states = [], {}
    for line in example['ingredients']:
        stock.append({'Item':line['name'],'Location':'Pantry','Unit':'g','Quantity':100000.0,'Status':'Available'})
        states['|'.join((line['name'].casefold(),'Pantry','g'))] = line['state']
    return {'week_start':'2026-10-12','input_version':1,'members':[{'id':member_id,'name':'Alex','kind':'Adult','age_group':'','targets':None,'restrictions':'','dislikes':''}],
        'inventory':stock,'recipes':recipes,'history_families':[],
        'settings':{'cuisines':['South Indian'],'cooking_effort':'simple','meal_prep':'none','busy_days':['Monday']},
        'options':clean_options({'web':False,'new_recipes':False,'vegetarian':False,'stock_states':states})}


def proposed_menu(catalog, members, servings=1):
    used, meals = set(), []
    for day in range(7):
        for kind in MEAL_TYPES:
            recipe = next(r for r in catalog if r['meal_type'] == kind and r['dish_family'] not in used)
            used.add(recipe['dish_family'])
            meals.append({'day':day,'meal_type':kind,'recipe_id':recipe['id'],'reason':'Fixture selection',
                'portions':[{'member_id':m['id'],'servings':servings} for m in members]})
    return {'meals':meals}


class FakePlanningModel:
    model = 'test-model'
    def __init__(self, mutate=None):
        self.calls, self.mutate = [], mutate

    def propose(self, instructions, data, schema, timeout=120):
        self.calls.append(deepcopy(data))
        if 'recipes' in schema.get('properties',{}):
            return {'recipes':[{'name':f"Proposed {data['meal_type']} {n}",'dish_family':f"proposed-{data['meal_type']}-{n}",
                'cuisine':'South Indian','servings':2,'effort':'simple','source_url':'','instructions':['Fixture preparation, review before cooking.'],
                'ingredients':[{'name':'Carrots','quantity':100,'unit':'g','state':'raw','component':'Main dish'}]}
                for n in range(data['count'])]}
        proposal = proposed_menu(data['recipes'],data['snapshot']['members'])
        return self.mutate(proposal,len(self.calls)) if self.mutate else proposal


def web_source():
    return {'title':'Fixture source recipe','url':'https://www.vegrecipesofindia.com/fixture-recipe/',
        'ingredients':['100 g carrots','1 cup rice'],'instructions':['Fixture preparation step.'],
        'category':'Breakfast','cuisine':'South Indian','yield':'3','source_hash':'fixture-hash'}


class PlanningTests(unittest.TestCase):
    def run_agent(self,snapshot=None,model=None,budget=None,web=None):
        saved, progress = [], []
        def save(document):
            saved.append(deepcopy(document))
            return document
        agent = PlanningAgent(model or FakePlanningModel(),web=web,budget=budget)
        state,message = agent.run(snapshot or planning_fixture(),progress.append,save)
        return state,message,saved,agent

    def test_full_week_calculates_shared_servings_without_consuming_stock(self):
        snapshot = planning_fixture()
        before = deepcopy(snapshot)
        state,_,saved,agent = self.run_agent(snapshot)
        self.assertEqual(state,'draft_ready')
        menu = saved[-1]['menu']
        self.assertEqual(len(menu['meals']),28)
        self.assertEqual(len({m['recipe_id'] for m in menu['meals']}),28)
        self.assertTrue(saved[-1]['report']['ready'])
        self.assertAlmostEqual(saved[-1]['report']['daily_totals'][0]['totals']['kcal'],1034.4)
        self.assertEqual(len(agent.model.calls),1)
        self.assertEqual(snapshot,before)

    def test_duplicate_finished_dish_is_revised_and_rechecked(self):
        def mutate(proposal,call):
            if call == 1:
                proposal['meals'][-1]['recipe_id'] = proposal['meals'][3]['recipe_id']
            return proposal
        state,_,saved,agent = self.run_agent(model=FakePlanningModel(mutate))
        self.assertEqual(state,'draft_ready')
        self.assertEqual(len(agent.model.calls),2)
        self.assertIn('duplicate_dish',[i['code'] for i in saved[1]['report']['issues']])
        self.assertNotEqual(saved[1]['report']['input_fingerprint'],saved[2]['report']['input_fingerprint'])
        self.assertEqual(saved[2]['report']['candidate_version_id'],saved[2]['menu']['version_id'])

    def test_known_target_deviations_drive_optimizer(self):
        snapshot = planning_fixture()
        snapshot['members'][0]['targets'] = {'kcal':1034.4,'protein':38.44,'carbs':180.01,'fat':19.24}
        def mutate(proposal,call):
            if call == 1:
                for meal in proposal['meals']:
                    meal['portions'][0]['servings'] = 2
            return proposal
        state,_,saved,agent = self.run_agent(snapshot,FakePlanningModel(mutate))
        self.assertEqual(state,'draft_ready')
        self.assertEqual(len(agent.model.calls),2)
        self.assertIn('target_deviation',[i['code'] for i in saved[1]['report']['issues']])
        self.assertNotIn('target_deviation',[i['code'] for i in saved[-1]['report']['issues']])

    def test_optimizer_retains_better_candidate_when_revision_regresses(self):
        snapshot = planning_fixture()
        snapshot['members'][0]['targets'] = {'kcal':1500,'protein':60,'carbs':200,'fat':30}
        def mutate(proposal,call):
            if call > 1:
                for meal in proposal['meals']:
                    meal['portions'][0]['servings'] = 4
            return proposal
        _,_,saved,_ = self.run_agent(snapshot,FakePlanningModel(mutate),AgentBudget(max_revisions=2))
        self.assertEqual(len(saved),4)
        self.assertAlmostEqual(saved[-1]['report']['daily_totals'][0]['totals']['kcal'],1500)
        self.assertNotEqual(saved[0]['menu']['version_id'],saved[-1]['menu']['version_id'])

    def test_child_quantitative_portions_are_not_invented(self):
        snapshot = planning_fixture()
        snapshot['members'].append({'id':'child','name':'Sam','kind':'Child','targets':None,'restrictions':''})
        state,_,saved,_ = self.run_agent(snapshot)
        self.assertEqual(state,'needs_input')
        self.assertTrue(all(p['member_id'] != 'child' for meal in saved[-1]['menu']['meals'] for p in meal['portions']))
        self.assertIn('missing_portions',[i['code'] for i in saved[-1]['report']['issues']])

    def test_new_recipes_are_unreviewed_and_have_no_invented_nutrition(self):
        snapshot = planning_fixture()
        snapshot['recipes'] = {}
        snapshot['options']['new_recipes'] = True
        state,_,saved,agent = self.run_agent(snapshot)
        self.assertEqual(state,'needs_input')
        self.assertEqual(len(saved[-1]['menu']['meals']),28)
        self.assertEqual(len(saved[-1]['unreviewed_ids']),28)
        self.assertEqual(len(agent.model.calls),5)
        self.assertTrue(all(line['food'] is None for r in saved[-1]['recipes'].values() for line in r['ingredients']))
        self.assertIsNone(saved[-1]['report']['daily_totals'][0]['totals']['kcal'])

    def test_insufficient_saved_pool_returns_specific_missing_input(self):
        snapshot = planning_fixture()
        snapshot['recipes'] = {}
        state,message,saved,agent = self.run_agent(snapshot)
        self.assertEqual(state,'needs_input')
        self.assertIn('7 more distinct breakfast',message)
        self.assertEqual(saved,[])
        self.assertEqual(agent.model.calls,[])

    def test_invalid_model_ids_can_be_repaired_within_the_bound(self):
        def mutate(proposal,call):
            if call == 1:
                proposal['meals'][0]['recipe_id'] = 'invented-id'
            return proposal
        state,_,_,agent = self.run_agent(model=FakePlanningModel(mutate))
        self.assertEqual(state,'draft_ready')
        self.assertEqual(len(agent.model.calls),2)

    def test_web_failure_retains_a_visible_note_without_fabricating_sources(self):
        snapshot = planning_fixture()
        snapshot['options']['web'] = True
        from unittest.mock import Mock
        web = Mock()
        web.search.side_effect = RecipeWebUnavailable('offline')
        _,_,saved,_ = self.run_agent(snapshot,web=web)
        self.assertEqual(saved[-1]['web_sources'],[])
        self.assertIn('unavailable',saved[-1]['web_notes'][0])

    def test_execution_budget_stops_before_model_calls(self):
        model = FakePlanningModel()
        with self.assertRaises(PlanningBudgetExceeded):
            self.run_agent(model=model,budget=AgentBudget(max_model_calls=0))
        self.assertEqual(model.calls,[])

    def test_package_counts_do_not_become_available_grams(self):
        snapshot = planning_fixture()
        snapshot['inventory'][0].update(Quantity=3,Unit='each')
        state,_,saved,_ = self.run_agent(snapshot)
        self.assertEqual(state,'draft_ready')
        chickpeas = next(row for row in saved[-1]['report']['shopping'] if row['canonical_name'] == 'chickpeas')
        self.assertIsNone(chickpeas['available_g'])
        self.assertIsNone(chickpeas['shortfall_g'])
        self.assertIn('stock_unknown',[i['code'] for i in saved[-1]['report']['issues']])

    def test_options_and_model_quantities_have_strict_bounds(self):
        with self.assertRaises(ValueError):
            clean_options({'web':'yes'})
        snapshot = planning_fixture()
        proposal = proposed_menu(list(snapshot['recipes'].values()),snapshot['members'])
        for value in (True,0,5,float('inf')):
            proposal['meals'][0]['portions'][0]['servings'] = value
            with self.assertRaises(ValueError):
                clean_proposal(proposal,snapshot['recipes'],snapshot['members'])

    def test_model_timeout_retains_complete_initial_candidate_and_visible_note(self):
        class BrokenModel(FakePlanningModel):
            def propose(self,*args,**kwargs):
                raise ReceiptModelUnavailable('Timed out')
        state,_,saved,_ = self.run_agent(model=BrokenModel())
        self.assertEqual(state,'draft_ready')
        self.assertEqual(len(saved[-1]['menu']['meals']),28)
        self.assertTrue(saved[-1]['report']['ready'])
        self.assertTrue(any('could not finish' in note for note in saved[-1]['web_notes']))

    def test_pending_recipe_pool_is_reused_but_remains_unreviewed(self):
        snapshot = planning_fixture()
        snapshot['proposal_recipes'] = snapshot['recipes']
        snapshot['recipes'] = {}
        snapshot['options']['new_recipes'] = True
        state,_,saved,agent = self.run_agent(snapshot)
        self.assertEqual(state,'needs_input')
        self.assertEqual(len(saved[-1]['menu']['meals']),28)
        self.assertEqual(len(saved[-1]['unreviewed_ids']),28)
        self.assertEqual(len(agent.model.calls),1)

    def test_renamed_south_indian_variants_do_not_bypass_uniqueness(self):
        snapshot = planning_fixture()
        recipes = list(snapshot['recipes'].values())
        recipes[0].update(name='Rava Idli',dish_family='custom-one')
        recipes[1].update(name='Vegetable Idli',dish_family='custom-two')
        menu = clean_proposal(proposed_menu(recipes,snapshot['members']),snapshot['recipes'],snapshot['members'])
        report = assess_candidate(snapshot,menu,snapshot['recipes'],[])
        self.assertFalse(report['ready'])
        self.assertIn('duplicate_finished_identity',[i['code'] for i in report['issues']])

    def test_local_adapter_places_instruction_and_schema_in_user_prompt(self):
        model = OllamaPlanner()
        with patch.object(model.client,'_request',side_effect=[{'capabilities':['completion']},
                {'done':True,'message':{'content':'{"recipes":[]}'}}]) as request:
            model.propose('Return exactly 4 recipes',{'count':4},RECIPE_SCHEMA)
        body = request.call_args_list[-1].args[1]
        self.assertIn('Return exactly 4 recipes',body['messages'][1]['content'])
        self.assertIn('Required output schema',body['messages'][1]['content'])
        self.assertFalse(body['think'])


class WebRecipeTests(unittest.TestCase):
    def test_nested_recipe_schema_preserves_source_text_and_hash(self):
        node = {'@graph':[{'@type':'Recipe','name':'Fixture source','recipeIngredient':['100 g carrots','1 cup rice'],
            'recipeInstructions':[{'@type':'HowToSection','itemListElement':[{'@type':'HowToStep','text':'<b>Prepare</b> the ingredients.'}]}],
            'recipeYield':'3','recipeCuisine':['South Indian'],'recipeCategory':['Breakfast']}]}
        payload = ('<script type="application/ld+json">' + json.dumps(node) + '</script>').encode()
        source = parse_recipe_page(payload,'https://www.vegrecipesofindia.com/fixture/')
        self.assertEqual(source['instructions'],['Prepare the ingredients.'])
        self.assertEqual(len(source['source_hash']),64)
        draft = source_to_draft(source,'Breakfast')
        self.assertEqual(draft['servings'],3)
        self.assertEqual(draft['ingredients'][0]['quantity'],100)
        self.assertIsNone(draft['ingredients'][1]['quantity'])
        self.assertFalse(draft['restriction_reviewed'])
        self.assertEqual(draft['source_ingredients'],source['ingredients'])

    def test_unsupported_hosts_and_unstructured_pages_are_rejected(self):
        for url in ('http://localhost/','https://localhost/','https://www.vegrecipesofindia.com.evil.test/','https://user:secret@www.vegrecipesofindia.com/'):
            with self.assertRaises(ValueError):
                checked_url(url)
        with self.assertRaises(RecipeWebUnavailable):
            parse_recipe_page(b'<html>No recipe</html>','https://www.vegrecipesofindia.com/fixture/')
