CREATE TABLE menuagent.recipe_versions (
    household_id uuid NOT NULL REFERENCES menuagent.households(id),
    recipe_id uuid NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    document jsonb NOT NULL CHECK (jsonb_typeof(document) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (household_id, recipe_id, revision)
);
CREATE TABLE menuagent.food_sources (
    household_id uuid NOT NULL REFERENCES menuagent.households(id),
    food_id text NOT NULL,
    document jsonb NOT NULL CHECK (jsonb_typeof(document) = 'object'),
    PRIMARY KEY (household_id, food_id)
);
ALTER TABLE menuagent.recipe_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE menuagent.recipe_versions FORCE ROW LEVEL SECURITY;
CREATE POLICY own_recipes ON menuagent.recipe_versions
    USING (household_id = nullif(current_setting('menuagent.household_id', true), '')::uuid
           AND EXISTS (SELECT 1 FROM menuagent.editor_access a WHERE a.household_id = recipe_versions.household_id
                       AND a.editor_subject = current_setting('menuagent.editor_subject', true)))
    WITH CHECK (household_id = nullif(current_setting('menuagent.household_id', true), '')::uuid
           AND EXISTS (SELECT 1 FROM menuagent.editor_access a WHERE a.household_id = recipe_versions.household_id
                       AND a.editor_subject = current_setting('menuagent.editor_subject', true)));
ALTER TABLE menuagent.food_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE menuagent.food_sources FORCE ROW LEVEL SECURITY;
CREATE POLICY own_food_sources ON menuagent.food_sources
    USING (household_id = nullif(current_setting('menuagent.household_id', true), '')::uuid
           AND EXISTS (SELECT 1 FROM menuagent.editor_access a WHERE a.household_id = food_sources.household_id
                       AND a.editor_subject = current_setting('menuagent.editor_subject', true)))
    WITH CHECK (household_id = nullif(current_setting('menuagent.household_id', true), '')::uuid
           AND EXISTS (SELECT 1 FROM menuagent.editor_access a WHERE a.household_id = food_sources.household_id
                       AND a.editor_subject = current_setting('menuagent.editor_subject', true)));
