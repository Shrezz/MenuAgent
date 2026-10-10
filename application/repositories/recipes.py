"""Household-scoped source cache and immutable recipe revisions."""
from copy import deepcopy
from uuid import UUID
from psycopg.types.json import Jsonb

from application.domain.recipes import clean_food, clean_recipe


class RecipeRepository:
    def __init__(self, household_repository):
        self.households = household_repository
        self.database, self.context = household_repository.database, household_repository.context

    def read(self):
        with self.database.transaction(self.context) as conn:
            rows = conn.execute('SELECT DISTINCT ON (recipe_id) document FROM menuagent.recipe_versions WHERE household_id = %s ORDER BY recipe_id, revision DESC', (self.context.household_id,)).fetchall()
            foods = conn.execute('SELECT food_id, document FROM menuagent.food_sources WHERE household_id = %s', (self.context.household_id,)).fetchall()
        return {row['document']['id']: row['document'] for row in rows}, {row['food_id']: row['document'] for row in foods}

    def revisions(self, recipe_id):
        recipe_id = str(UUID(recipe_id))
        with self.database.transaction(self.context) as conn:
            return [row['document'] for row in conn.execute('SELECT document FROM menuagent.recipe_versions WHERE household_id = %s AND recipe_id = %s ORDER BY revision', (self.context.household_id, recipe_id)).fetchall()]

    def save(self, document, expected_version):
        document = clean_recipe(document)
        with self.database.transaction(self.context) as conn:
            household_version = self.households._advance(conn, expected_version)
            revision = conn.execute('SELECT coalesce(max(revision), 0) + 1 AS next FROM menuagent.recipe_versions WHERE household_id = %s AND recipe_id = %s', (self.context.household_id, document['id'])).fetchone()['next']
            saved = dict(document, revision=revision)
            conn.execute('INSERT INTO menuagent.recipe_versions (household_id, recipe_id, revision, document) VALUES (%s, %s, %s, %s)', (self.context.household_id, saved['id'], revision, Jsonb(saved)))
        return deepcopy(saved), household_version

    def save_food(self, food, expected_version):
        food = clean_food(food)
        with self.database.transaction(self.context) as conn:
            version = self.households._advance(conn, expected_version)
            conn.execute('INSERT INTO menuagent.food_sources (household_id, food_id, document) VALUES (%s, %s, %s) ON CONFLICT (household_id, food_id) DO UPDATE SET document = EXCLUDED.document', (self.context.household_id, food['id'], Jsonb(food)))
        return version
