# MenuAgent application and agent structure

The project separates UI, domain validation, household persistence and the planning agent. PostgreSQL persistence, source-backed calculations, local automatic planning and South Indian vegetarian web discovery are implemented. Finalized-menu editing and inventory reservations remain future work.

    menuagent/
    ├── plan.MD                         Working MVP baseline, version 2
    ├── README.md                       Setup, preview scope and next steps
    ├── PROGRESS.md                     Completed work, verification and next milestones
    ├── requirements.txt                Streamlit, PostgreSQL and Pillow dependencies
    ├── streamlit_app.py                 Navigation and shared application shell
    ├── .streamlit/config.toml           UI theme and local runtime settings
    ├── application/
    │   ├── ui/
    │   │   ├── components.py           Shared display helpers and service access
    │   │   ├── receipt_review.py       Real uploaded-image reading and review
    │   │   ├── planning.py             Job progress, automatic drafts and recipe review
    │   │   └── pages/
    │   │       ├── week.py             Menu, portions, prep, freezer and shopping
    │   │       ├── groceries.py        Receipt review and stock editing
    │   │       ├── recipes.py          Search, categories and feedback
    │   │       ├── household.py        Individual profiles and shared settings
    │   │       └── history.py          Stored automatic drafts and session previews
    │   ├── services/
    │   │   ├── demo.py                 Session-only UI service and sample fixtures
    │   │   ├── households.py           Durable household service with sample menu preview
    │   │   ├── receipts.py             Local extraction and reviewed purchase facade
    │   │   ├── recipes.py              Versioned recipe library facade
    │   │   ├── menus.py                Planning options, queueing and worker dispatch
    │   │   └── recipe_examples.py      Optional original editor example
    │   ├── config.py                  Private backend configuration and mode selection
    │   ├── repositories/
    │   │   ├── households.py           Household-scoped transactions and version checks
    │   │   ├── receipts.py             Atomic confirmation and duplicate protection
    │   │   ├── recipes.py              Immutable recipe revisions and source cache
    │   │   └── menus.py                Immutable snapshots/candidates and scoped jobs
    │   └── domain/
    │       ├── models.py               Framework-independent household/preview records
    │       ├── households.py           Profile, settings and inventory input validation
    │       ├── recipes.py              Structured recipe/food validation and normalization
    │       ├── receipts.py             Extraction schema and purchase merging
    │       ├── nutrition.py            Source-backed arithmetic and portions
    │       └── planning.py             Pure candidate validation and daily totals
    ├── agent/
    │   ├── contracts.py                Planning request, issue and result records
    │   ├── runtime.py                  Retrieval, proposals, evaluation and bounded repair
    │   ├── state.py                    Model, tool, fetch and elapsed budgets
    │   ├── README.md                   Agent boundary and implementation notes
    │   ├── prompts/planner.md          Planning instructions
    │   └── tools/                     Checklist and calculations.py tool facade
    ├── integrations/
    │   ├── ollama.py                   Local-only receipt vision adapter
    │   ├── ollama_planner.py           Local structured text-model requests
    │   ├── recipe_web.py               Publisher search, JSON-LD import and provenance
    │   ├── usda.py                     Reviewed USDA lookup and parsing
    │   └── data/                       Offline source snapshots and retained responses
    ├── database/
    │   ├── connection.py              Trusted household/editor transaction context
    │   ├── migrations/001_household_records.sql  Tables and row-level policies
    │   ├── migrations/002_cooking_preferences.sql  Effort, prep and busier days
    │   ├── migrations/003_recipe_library.sql  Recipes, sources and row policies
    │   ├── migrations/004_receipt_review.sql  Images, extraction and confirmation
    │   ├── migrations/005_planning_jobs.sql  Job snapshots and immutable candidates
    │   ├── manage.py                  Migration and editor provisioning commands
    │   ├── local.py                   Local setup/start/stop/status commands
    │   ├── docker_local.py            Persistent isolated Docker database
    │   └── test.py                    Isolated PostgreSQL test-suite runner
    ├── workers/
    │   └── planning.py                 Local background worker, cancellation and CLI
    ├── docs/
    │   ├── directory-structure.md
    │   ├── database.md                Setup, ownership and persistence boundaries
    │   ├── receipts-and-ollama.md       Local model choice and receipt contracts
    │   ├── recipes-and-nutrition.md    Editor, sources and calculation contracts
    │   ├── automatic-planning.md       Application/agent loop, web sources and limits
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
        ├── test_receipts.py             Model contracts and purchase quantities
        ├── test_recipe_calculations.py  Source/portion/full-week arithmetic fixtures
        └── test_planning.py            Model repair, draft review and publisher contracts

Implementation status and subsequent work:

| Location | Responsibility |
| --- | --- |
| application/services/households.py | Implemented: profile persistence and household settings |
| application/services/receipts.py | Implemented: local extraction, editable review and once-only purchase confirmation |
| application/services/menus.py | Implemented: automatic job queueing and stored drafts; candidate edits and finalization pending |
| application/domain/nutrition.py | Implemented: sourced ingredient and portion arithmetic |
| application/domain/inventory.py | Allocation, reservations and cooking events |
| application/domain/planning.py and agent/runtime.py | Implemented: restrictions, duplicates, workload, completeness and nutrient checks |
| application/repositories/ | Household, recipe, receipt and planning repositories implemented |
| agent/runtime.py and agent/state.py | Implemented: bounded evaluator/optimizer loop and retained best candidate |
| agent/tools/registry.py | Optional future dynamic tool selection; current runtime uses explicit application calls |
| integrations/ | Local Ollama receipt/planning, USDA lookup and publisher recipe search/import implemented; reviewed food guidance pending |
| workers/planning.py | Implemented: durable local job lifecycle, snapshots, repair and cancellation; production supervision pending |
| database/migrations/ | Migrations 001–005 implemented; later milestones add numbered migrations |

Streamlit pages call application services directly. The worker executes the bounded agent loop against application repositories and calculation functions. Introduce a separate HTTP API when another frontend or independent deployment needs it.
