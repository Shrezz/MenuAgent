CREATE TABLE menuagent.planning_jobs (
    household_id uuid NOT NULL REFERENCES menuagent.households(id),
    id uuid NOT NULL,
    week_start date NOT NULL,
    input_version bigint NOT NULL,
    request_key text NOT NULL,
    snapshot jsonb NOT NULL,
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','needs_input','draft_ready','failed','cancelled')),
    progress text NOT NULL DEFAULT 'Waiting for the planner',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (household_id, id),
    UNIQUE (household_id, request_key)
);
CREATE TABLE menuagent.menu_candidates (
    household_id uuid NOT NULL,
    id uuid NOT NULL,
    job_id uuid NOT NULL,
    document jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (household_id, id),
    FOREIGN KEY (household_id, job_id) REFERENCES menuagent.planning_jobs(household_id, id)
);
ALTER TABLE menuagent.planning_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE menuagent.planning_jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY own_planning_jobs ON menuagent.planning_jobs
    USING (household_id = nullif(current_setting('menuagent.household_id', true), '')::uuid
       AND EXISTS (SELECT 1 FROM menuagent.editor_access a WHERE a.household_id = planning_jobs.household_id
                   AND a.editor_subject = current_setting('menuagent.editor_subject', true)))
    WITH CHECK (household_id = nullif(current_setting('menuagent.household_id', true), '')::uuid
       AND EXISTS (SELECT 1 FROM menuagent.editor_access a WHERE a.household_id = planning_jobs.household_id
                   AND a.editor_subject = current_setting('menuagent.editor_subject', true)));
ALTER TABLE menuagent.menu_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE menuagent.menu_candidates FORCE ROW LEVEL SECURITY;
CREATE POLICY own_menu_candidates ON menuagent.menu_candidates
    USING (household_id = nullif(current_setting('menuagent.household_id', true), '')::uuid
       AND EXISTS (SELECT 1 FROM menuagent.editor_access a WHERE a.household_id = menu_candidates.household_id
                   AND a.editor_subject = current_setting('menuagent.editor_subject', true)))
    WITH CHECK (household_id = nullif(current_setting('menuagent.household_id', true), '')::uuid
       AND EXISTS (SELECT 1 FROM menuagent.editor_access a WHERE a.household_id = menu_candidates.household_id
                   AND a.editor_subject = current_setting('menuagent.editor_subject', true)));
