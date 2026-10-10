# MenuAgent

Streamlit household menu planner with durable household records, a structured recipe library, source-backed nutrition calculations and a sample weekly-menu preview. The product baseline is plan.MD version 2, archived in docs/plans/plan-v2.MD. The original version 1 remains unchanged.

## Run locally

Python 3.12 is the tested runtime. From this directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m database.local setup
.venv/bin/python -m streamlit run streamlit_app.py
```

Setup prefers Docker when its daemon is available; otherwise it uses PostgreSQL CLI tools on PATH. Select --backend docker or --backend native explicitly if needed. Docker setup creates a project-specific PostgreSQL 17 container and persistent volume, bound to 127.0.0.1:55432. Native setup creates a private socket-only cluster. Existing unrelated databases are not modified.

The app uses the private local configuration after setup. Start on **Household**, add members and optional daily targets, then save cooking preferences. Add fridge, pantry and freezer items under **Groceries & stock → Kitchen stock**. A new household starts empty; sample profiles, stock and recipes are not seeded into it. Under Recipes, load the optional example into the editor and explicitly save it to try the portion calculator.

```sh
.venv/bin/python -m database.local status
.venv/bin/python -m database.local stop
.venv/bin/python -m database.local start
```

Stop retains database records and the Docker volume. Local editor mode requires Streamlit's loopback binding. Remote access requires configured authentication; see docs/database.md.

## Implemented

- PostgreSQL migrations and household-scoped repositories for profiles, preferences and kitchen stock.
- Add/edit adult and child profiles; optional manually entered calorie and macro targets; children start without numeric targets.
- Shared cuisines, usual cooking effort, weekly meal-prep preference and recurring busier days. Unentered preferences remain unset; recipe times are guidance rather than a pass/fail budget.
- Ingredient quantities, location, unit and status; untracked staples retain unknown quantities.
- Transactional saves, optimistic versions, row-level access policies and a non-administrative application role.
- Saved-record reload and persistence across new browser sessions. Menu-preview resets retain household records.
- Durable recipe editor and collection with quantities, yields, source snapshots and immutable revisions.
- Reviewed USDA food matching with nine offline source records and optional backend-key live lookup.
- Deterministic recipe and portion nutrition calculations, plus candidate-validation tools for the upcoming planner.
- Five pages with the original sample weekly menu, swaps, locks, portion controls and session history.

Saved cooking preferences do not yet adapt sample menus. Put and forget recipes (Instant Pot and source-verified overnight options) are planned for phase 2.

Real receipt extraction, automatic recipe imports, the planning agent and durable menu history remain pending. The weekly preview does not yet use the saved recipe library or its calculations. Child food-variety guidance and normalized stock reconciliation remain explicit review requirements for the upcoming planning runtime. Dietary restrictions are stored but are not yet enforced against the sample menu. Sample receipt confirmation uses a separate session-only stock preview in persistent mode, keeping sample purchases out of actual stock.

## Preview without a database

```sh
MENUAGENT_MODE=preview .venv/bin/python -m streamlit run streamlit_app.py
```

This uses sample household records and session-only storage. The sidebar states which data is saved and which remains a preview. Without a configured database the app defaults to preview mode. A configured but unavailable database displays an error rather than falling back to sample data.

## Validation

```sh
.venv/bin/python -m database.test
```

The runner creates an isolated test database, runs the suite and removes that test database. It does not edit the household used by the app. The current milestone passes 59 tests against PostgreSQL, including household isolation, stale saves, rollback, revoked access and Streamlit persistence across new sessions.

Without integration configuration, python -m unittest discover -s tests runs unit/preview tests and reports database tests as skipped. External test environments can supply MENUAGENT_TEST_ADMIN_DATABASE_URL and MENUAGENT_TEST_DATABASE_URL; see docs/database.md.

## Documentation

- PROGRESS.md: completed chunks and remaining milestones, numbered to match plan.MD.
- docs/database.md: database setup, access, configuration and testing.
- docs/recipes-and-nutrition.md: recipe editor, calculation contracts, source provenance and current boundaries.
- docs/directory-structure.md: implemented modules and future agent modules.
- docs/framework-options.md: frontend choices.
- docs/screenshots/: original UI preview captures.

Private runtime configuration and generated development credentials live under ignored .local/, with private filesystem permissions. API keys, .env files and credentials must remain outside version control.
