CREATE SCHEMA IF NOT EXISTS menuagent;

CREATE TABLE menuagent.households (
    id uuid PRIMARY KEY,
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 120),
    cuisines text[] NOT NULL DEFAULT '{}',
    daily_minutes integer CHECK (daily_minutes BETWEEN 10 AND 180),
    batch_minutes integer CHECK (batch_minutes BETWEEN 0 AND 180),
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Provisioned by an administrator, never writable by the application role.
CREATE TABLE menuagent.editor_access (
    household_id uuid NOT NULL REFERENCES menuagent.households(id),
    editor_subject text NOT NULL CHECK (length(btrim(editor_subject)) > 0),
    PRIMARY KEY (household_id, editor_subject)
);

CREATE TABLE menuagent.members (
    household_id uuid NOT NULL REFERENCES menuagent.households(id),
    id uuid NOT NULL,
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 120),
    kind text NOT NULL CHECK (kind IN ('Adult', 'Child')),
    age_group text NOT NULL DEFAULT '',
    targets jsonb,
    dislikes text NOT NULL DEFAULT '',
    restrictions text NOT NULL DEFAULT '',
    PRIMARY KEY (household_id, id),
    CHECK ((kind = 'Adult' AND age_group = '') OR
           (kind = 'Child' AND age_group IN ('Toddler', 'Preschool', 'School age', 'Teen'))),
    CHECK (targets IS NULL OR (
        jsonb_typeof(targets) = 'object' AND
        targets ?& ARRAY['kcal', 'protein', 'carbs', 'fat'] AND
        jsonb_typeof(targets->'kcal') = 'number' AND (targets->>'kcal')::numeric > 0 AND
        jsonb_typeof(targets->'protein') = 'number' AND (targets->>'protein')::numeric > 0 AND
        jsonb_typeof(targets->'carbs') = 'number' AND (targets->>'carbs')::numeric > 0 AND
        jsonb_typeof(targets->'fat') = 'number' AND (targets->>'fat')::numeric > 0
    ))
);

CREATE TABLE menuagent.inventory_items (
    household_id uuid NOT NULL REFERENCES menuagent.households(id),
    item_key text NOT NULL,
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 160),
    location text NOT NULL CHECK (location IN ('Fridge', 'Pantry', 'Freezer')),
    unit text NOT NULL CHECK (unit IN ('g', 'ml', 'each')),
    quantity double precision CHECK (quantity >= 0 AND quantity < 'Infinity'::double precision),
    status text NOT NULL CHECK (status IN ('Available', 'Use soon', 'Low', 'Out')),
    position integer NOT NULL CHECK (position >= 0),
    PRIMARY KEY (household_id, item_key, location, unit)
);

ALTER TABLE menuagent.editor_access ENABLE ROW LEVEL SECURITY;
ALTER TABLE menuagent.editor_access FORCE ROW LEVEL SECURITY;
CREATE POLICY own_editor_access ON menuagent.editor_access
    FOR SELECT USING (editor_subject = current_setting('menuagent.editor_subject', true));

ALTER TABLE menuagent.households ENABLE ROW LEVEL SECURITY;
ALTER TABLE menuagent.households FORCE ROW LEVEL SECURITY;
CREATE POLICY own_household ON menuagent.households
    USING (id = nullif(current_setting('menuagent.household_id', true), '')::uuid
           AND EXISTS (SELECT 1 FROM menuagent.editor_access a
                       WHERE a.household_id = id
                         AND a.editor_subject = current_setting('menuagent.editor_subject', true)))
    WITH CHECK (id = nullif(current_setting('menuagent.household_id', true), '')::uuid
                AND EXISTS (SELECT 1 FROM menuagent.editor_access a
                            WHERE a.household_id = id
                              AND a.editor_subject = current_setting('menuagent.editor_subject', true)));

ALTER TABLE menuagent.members ENABLE ROW LEVEL SECURITY;
ALTER TABLE menuagent.members FORCE ROW LEVEL SECURITY;
CREATE POLICY own_members ON menuagent.members
    USING (household_id = nullif(current_setting('menuagent.household_id', true), '')::uuid
           AND EXISTS (SELECT 1 FROM menuagent.editor_access a
                       WHERE a.household_id = members.household_id
                         AND a.editor_subject = current_setting('menuagent.editor_subject', true)))
    WITH CHECK (household_id = nullif(current_setting('menuagent.household_id', true), '')::uuid
                AND EXISTS (SELECT 1 FROM menuagent.editor_access a
                            WHERE a.household_id = members.household_id
                              AND a.editor_subject = current_setting('menuagent.editor_subject', true)));

ALTER TABLE menuagent.inventory_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE menuagent.inventory_items FORCE ROW LEVEL SECURITY;
CREATE POLICY own_inventory ON menuagent.inventory_items
    USING (household_id = nullif(current_setting('menuagent.household_id', true), '')::uuid
           AND EXISTS (SELECT 1 FROM menuagent.editor_access a
                       WHERE a.household_id = inventory_items.household_id
                         AND a.editor_subject = current_setting('menuagent.editor_subject', true)))
    WITH CHECK (household_id = nullif(current_setting('menuagent.household_id', true), '')::uuid
                AND EXISTS (SELECT 1 FROM menuagent.editor_access a
                            WHERE a.household_id = inventory_items.household_id
                              AND a.editor_subject = current_setting('menuagent.editor_subject', true)));
