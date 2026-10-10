"""Shared recipe UI facade, with PostgreSQL or explicit session-only preview."""
from copy import deepcopy
from application.domain.recipes import clean_food, clean_recipe
from application.repositories.recipes import RecipeRepository
from integrations.usda import bundled_foods


class RecipeLibrary:
    def __init__(self, owner):
        self.owner = owner
        self.repository = RecipeRepository(owner.repository) if owner.persistent else None
        self.refresh()

    def refresh(self):
        self.foods = bundled_foods()
        if self.repository:
            self.recipes, imported = self.repository.read()
            self.foods.update(imported)
        else:
            self.recipes = {}
            self.history = {}

    def save(self, document):
        document = clean_recipe(document)
        if self.repository:
            saved, version = self.repository.save(document, self.owner.household_version)
            self.owner.household_version = version
        else:
            saved = dict(document, revision=self.recipes.get(document['id'], {}).get('revision', 0) + 1)
            self.history.setdefault(saved['id'], []).append(deepcopy(saved))
        self.recipes[saved['id']] = saved
        return saved

    def save_food(self, food):
        food = clean_food(food)
        if self.repository:
            self.owner.household_version = self.repository.save_food(food, self.owner.household_version)
        self.foods[food['id']] = food

    def revisions(self, recipe_id):
        return self.repository.revisions(recipe_id) if self.repository else deepcopy(self.history.get(recipe_id, []))
