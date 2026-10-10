CREATE TABLE menuagent.receipts (
    household_id uuid NOT NULL REFERENCES menuagent.households(id),
    image_hash text NOT NULL CHECK (image_hash ~ '^[0-9a-f]{64}$'),
    image_bytes bytea NOT NULL CHECK (octet_length(image_bytes) BETWEEN 1 AND 8388608),
    mime text NOT NULL CHECK (mime IN ('image/png', 'image/jpeg')),
    model text NOT NULL,
    extraction jsonb NOT NULL CHECK (jsonb_typeof(extraction) = 'object'),
    reviewed_items jsonb CHECK (jsonb_typeof(reviewed_items) = 'array'),
    created_at timestamptz NOT NULL DEFAULT now(),
    confirmed_at timestamptz,
    CHECK ((confirmed_at IS NULL) = (reviewed_items IS NULL)),
    PRIMARY KEY (household_id, image_hash)
);
ALTER TABLE menuagent.receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE menuagent.receipts FORCE ROW LEVEL SECURITY;
CREATE POLICY own_receipts ON menuagent.receipts
    USING (household_id = nullif(current_setting('menuagent.household_id', true), '')::uuid
           AND EXISTS (SELECT 1 FROM menuagent.editor_access a WHERE a.household_id = receipts.household_id
                       AND a.editor_subject = current_setting('menuagent.editor_subject', true)))
    WITH CHECK (household_id = nullif(current_setting('menuagent.household_id', true), '')::uuid
           AND EXISTS (SELECT 1 FROM menuagent.editor_access a WHERE a.household_id = receipts.household_id
                       AND a.editor_subject = current_setting('menuagent.editor_subject', true)));
