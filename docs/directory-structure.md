# MenuAgent application and agent structure

The project separates UI, domain validation, household persistence and the planning-agent boundary. PostgreSQL household persistence is implemented; recipe/nutrition integrations and the planning worker remain future milestones.

    menuagent/
    ├── plan.MD                         Working MVP baseline, version 1
    ├── README.md                       Setup, preview scope and next steps
    ├── PROGRESS.md                     Completed work, verification and next milestones
    ├── requirements.txt                Streamlit UI dependency
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
    │   │   └── households.py           Durable household service with sample menu preview
    │   ├── config.py                  Private backend configuration and mode selection
    │   ├── repositories/
    │   │   └── households.py           Household-scoped transactions and version checks
    │   └── domain/
    │       ├── models.py               Framework-independent household/preview records
    │       └── households.py           Profile, settings and inventory input validation
    ├── agent/
    │   ├── contracts.py                Planning request, issue and result records
    │   ├── README.md                   Agent boundary and implementation notes
    │   ├── prompts/planner.md          Planning instructions
    │   └── tools/README.md             Tool implementation checklist
    ├── integrations/                   Prepared directory for external adapters
    ├── database/
    │   ├── connection.py              Trusted household/editor transaction context
    │   ├── migrations/001_household_records.sql  Tables and row-level policies
    │   ├── manage.py                  Migration and editor provisioning commands
    │   ├── local.py                   Local setup/start/stop/status commands
    │   ├── docker_local.py            Persistent isolated Docker database
    │   └── test.py                    Isolated PostgreSQL test-suite runner
    ├── workers/                        Prepared directory for job execution
    ├── docs/
    │   ├── directory-structure.md
    │   ├── database.md                Setup, ownership and persistence boundaries
    │   ├── framework-options.md
    │   ├── screenshots/               Captures from the running UI preview
    │   └── plans/
    │       ├── README.md               Plan version policy
    │       └── plan-v1.MD              Archived version 1 baseline
    └── tests/
        ├── test_demo_service.py        State and interaction invariants
        ├── test_ui_flows.py            Preview widget/rerun checks
        ├── test_household_validation.py  Shared input invariants
        └── test_household_postgres.py  Real transactions, access and new-session UI checks

Planned modules for subsequent implementation:

| Location | Responsibility |
| --- | --- |
| application/services/households.py | Implemented: profile persistence and household settings |
| application/services/receipts.py | Review and idempotent purchase confirmation |
| application/services/menus.py | Candidate edits, finalization and history |
| application/domain/nutrition.py | Sourced ingredient and portion arithmetic |
| application/domain/inventory.py | Allocation, reservations and cooking events |
| application/domain/validation.py | Restrictions, duplicates, workload and completeness |
| application/repositories/ | Household repository implemented; recipe/receipt/menu repositories remain pending |
| agent/runtime.py and agent/state.py | Bounded planning loop and candidate state |
| agent/tools/registry.py | Tool registration and typed execution |
| integrations/ | Receipt extraction, recipe search/import, food data and guidance |
| workers/planning.py | Durable job lifecycle, retries, snapshots and cancellation |
| database/migrations/ | Household schema implemented; subsequent milestones add numbered migrations |

For the first persistent version, Streamlit pages can call application services directly. The worker calls the same services through agent tools. Introduce a separate HTTP API when another frontend or independent deployment needs it.
