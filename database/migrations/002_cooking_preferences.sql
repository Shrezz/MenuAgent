-- Retain historical minute budgets without inferring a cook's effort preference.
ALTER TABLE menuagent.households
    ADD COLUMN cooking_effort text CHECK (cooking_effort IN ('assembly', 'simple', 'flexible')),
    ADD COLUMN meal_prep text CHECK (meal_prep IN ('none', 'small', 'larger')),
    ADD COLUMN busy_days text[] NOT NULL DEFAULT '{}' CHECK (
        busy_days <@ ARRAY['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']::text[]
        AND array_position(busy_days, NULL) IS NULL
    );
