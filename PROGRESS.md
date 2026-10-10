# MenuAgent implementation progress

Updated: October 9, 2026

## Current milestone: Household persistence v0.2

Implementation chunk 2 is complete: household/database persistence, corresponding to **milestone 1: Household records** in plan.MD. The UI prototype was implementation chunk 1; it preceded the plan's numbered backend milestones.

The original remaining-work list in this file used different numbering. The table below now follows plan.MD exactly. Receipt extraction belongs to milestone 4; recipes and calculations belong to milestone 2. The product scope and archived version 1 remain unchanged.

## Completed in chunk 2

- PostgreSQL schema migrations, checksum tracking, repeatable migration execution and administrative household/editor provisioning.
- Durable member profiles, optional manually entered adult/child targets, age groups, dislikes and restrictions.
- Durable shared cuisines and cooking/batch budgets. New households have no assumed members, targets, stock or cooking budgets.
- Durable fridge/pantry/freezer stock with supported units, availability states and unknown quantities for untracked staples.
- Add/edit profile and stock forms connected to repositories; records survive fresh Streamlit browser sessions.
- Household-scoped queries and PostgreSQL row policies that check editor membership. Runtime rejects administrative database roles.
- Atomic stock replacement and version checks so stale sessions cannot overwrite newer edits.
- Access checked on each application rerun, including after editor access is revoked. Saved-record reload clears stale form values.
- One local editor behind a loopback listener. Optional OIDC wiring requires provider configuration and provisioned editor membership; a real provider login is not yet verified.
- Private PostgreSQL setup/start/stop/status commands. Docker setup and integration tests run successfully here. Native startup is offered for other environments but could not be exercised because this workspace blocks native shared-memory allocation.
- Sample receipt confirmation disabled for persistent households. Menu-preview resets retain saved household records.

## Previously completed: UI prototype v0.1

- Five pages: weekly menu, groceries/stock, categorized recipes, household profiles and history.
- Seven days of breakfast, lunch, dinner and snacks, with shared dishes for one cook.
- Day/week views, portion controls, swaps, locks and sample draft regeneration.
- Separate sample receipt review and duplicate-confirmation prevention in preview mode.
- Checks for all 28 slots, distinct sample dishes and daily sample active cooking time.
- Finalized sample-menu snapshots unaffected by later edits, within the browser session.
- Sample preparation, freezer and shopping suggestions, with pending quantities labeled.
- Agent request/result contracts, planner instructions and tool checklist.
- Version 1 handoff and identical archive, preserving all four Mermaid diagrams.
- Seven original screenshots in docs/screenshots/.

## Verification

Tested with Python 3.12, Streamlit 1.65.0 and real PostgreSQL 17. The full suite passes **32 tests**, including new-session profile/preference/stock persistence, household isolation through repositories and raw SQL, forged household access, access revocation, blocked self-provisioning, unsafe role rejection, stale saves, transaction rollback, unknown quantities, all five pages with an empty persistent household and the existing preview flows.

```sh
python -m database.local setup
python -m database.test
```

The runner creates a separate test database and removes it afterward. Application household records are not test fixtures. Basic unittest discovery skips integration cases unless both test database URLs are configured.

## MVP milestones — same numbering as plan.MD

| Milestone | Status and remaining work |
| --- | --- |
| 1 Household records | Complete for one local editor: PostgreSQL migrations, editor scoping, profiles, shared settings and manual stock. Remote identity-provider setup and verification remain deployment work. |
| 2 Recipes and calculations | Next: structured recipes, normalized ingredients, sourced nutrients, yields, member portions and deterministic validation. Fixtures must produce reproducible totals and expose missing data. |
| 3 Planning loop | Pending: background worker, snapshots, tools, bounded evaluator/optimizer revisions and checked seven-day drafts. The illustrative loop from chat is not installed. |
| 4 Receipt and discovery inputs | Pending: editable extraction, normalized review, durable duplicate handling, purchase confirmation, discovery/import and provenance. |
| 5 Weekly use | Pending: recalculating swaps/locks, prep/shopping/freezer tasks, durable recipe/menu snapshots, reservations, cooking/skip events and feedback. |
| 6 MVP verification | Pending: full end-to-end acceptance scenarios, deployment configuration and integration checks. |

The app now stores household inputs. Menus, recipe records, ratings and preview history remain session-based samples. There is no AI planner, receipt extraction or nutrition calculation yet. Stored restrictions do not validate sample menus yet. These remain within the version 1 MVP scope.
