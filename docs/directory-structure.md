# MenuAgent application and agent structure

The project separates UI, domain validation, household persistence and the planning-agent boundary. PostgreSQL household/recipe persistence and source-backed calculations are implemented; the planning worker remains the next milestone.

    menuagent/
    ├── plan.MD                         Working MVP baseline, version 2
    ├── README.md                       Setup, preview scope and next steps
    ├── PROGRESS.md                     Completed work, verification and next milestones
    ├── requirements.txt                Streamlit and PostgreSQL dependencies
    ├── streamlit_app.py                 Navigation and shared application shell
    ├── .streamlit/config.toml           UI theme and local runtime settings
    ├── application/
    │   ├── ui/
    │   │   ├── components.py           Shared display helpers and service access
    │   │   └── pages/
    │   │       ├── week.py             Menu, portions, prep, freezer and shopping
    │   │       ├── groceries.py        Receipt review and stock editing
    │   │       ├── recipes.py          Search, categories and feedback
    │   │       ├── household.py        Individual profiles and shared settings
    │   │       └── history.py          Saved preview versions
    │   ├── services/
    │   │   ├── demo.py                 Session-only UI service and sample fixtures
    │   │   ├── households.py           Durable household service with sample menu preview
    │   │   ├── recipes.py              Versioned recipe library facade
    │   │   └── recipe_examples.py      Optional original editor example
    │   ├── config.py                  Private backend configuration and mode selection
    │   ├── repositories/
    │   │   ├── households.py           Household-scoped transactions and version checks
    │   │   └── recipes.py              Immutable recipe revisions and source cache
    │   └── domain/
    │       ├── models.py               Framework-independent household/preview records
    │       ├── households.py           Profile, settings and inventory input validation
    │       ├── recipes.py              Structured recipe/food validation and normalization
    │       ├── nutrition.py            Source-backed arithmetic and portions
    │       └── planning.py             Pure candidate validation and daily totals
    ├── agent/
    │   ├── contracts.py                Planning request, issue and result records
    │   ├── README.md                   Agent boundary and implementation notes
    │   ├── prompts/planner.md          Planning instructions
    │   └── tools/                     Checklist and calculations.py tool facade
    ├── integrations/
    │   ├── usda.py                     Reviewed USDA lookup and parsing
    │   └── data/                       Offline source snapshots and retained responses
    ├── database/
    │   ├── connection.py              Trusted household/editor transaction context
    │   ├── migrations/001_household_records.sql  Tables and row-level policies
    │   ├── migrations/002_cooking_preferences.sql  Effort, prep and busier days
    │   ├── migrations/003_recipe_library.sql  Recipes, sources and row policies
    │   ├── manage.py                  Migration and editor provisioning commands
    │   ├── local.py                   Local setup/start/stop/status commands
    │   ├── docker_local.py            Persistent isolated Docker database
    │   └── test.py                    Isolated PostgreSQL test-suite runner
    ├── workers/                        Prepared directory for job execution
    ├── docs/
    │   ├── directory-structure.md
    │   ├── database.md                Setup, ownership and persistence boundaries
    │   ├── recipes-and-nutrition.md    Editor, sources and calculation contracts
    │   ├── framework-options.md
    │   ├── screenshots/               Captures from the running UI preview
    │   └── plans/
    │       ├── README.md               Plan version policy
    │       ├── plan-v1.MD              Original baseline, unchanged
    │       └── plan-v2.MD              Cooking preferences and phase 2 scope
    └── tests/
        ├── test_demo_service.py        State and interaction invariants
        ├── test_ui_flows.py            Preview widget/rerun checks
        ├── test_household_validation.py  Shared input invariants
        ├── test_household_postgres.py  Real transactions, access and new-session UI checks
        └── test_recipe_calculations.py  Source/portion/full-week arithmetic fixtures

Planned modules for subsequent implementation:

| Location | Responsibility |
| --- | --- |
| application/services/households.py | Implemented: profile persistence and household settings |
| application/services/receipts.py | Review and idempotent purchase confirmation |
| application/services/menus.py | Candidate edits, finalization and history |
| application/domain/nutrition.py | Implemented: sourced ingredient and portion arithmetic |
| application/domain/inventory.py | Allocation, reservations and cooking events |
| application/domain/validation.py | Restrictions, duplicates, workload and completeness |
| application/repositories/ | Household and recipe repositories implemented; receipt/menu repositories remain pending |
| agent/runtime.py and agent/state.py | Bounded planning loop and candidate state |
| agent/tools/registry.py | Tool registration and typed execution |
| integrations/ | Receipt extraction, recipe search/import, food data and guidance |
| workers/planning.py | Durable job lifecycle, retries, snapshots and cancellation |
| database/migrations/ | Household schema implemented; subsequent milestones add numbered migrations |

For the first persistent version, Streamlit pages can call application services directly. The worker calls the same services through agent tools. Introduce a separate HTTP API when another frontend or independent deployment needs it.
