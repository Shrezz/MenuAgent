# MenuAgent implementation progress

Updated: October 9, 2026

## Current milestone: Recipes and calculations v0.3

Implementation chunk 3 is complete: the recipe library and calculation foundation, corresponding to **milestone 2: Recipes and calculations** in plan.MD. Chunk 2 completed household/database persistence (milestone 1). The UI prototype was implementation chunk 1; it preceded the plan's numbered backend milestones.

The original remaining-work list in this file used different numbering. The table below now follows plan.MD exactly. Receipt extraction belongs to milestone 4; recipes and calculations belong to milestone 2. Archived version 1 remains unchanged. The agreed cooking-preference revision is recorded in plan.MD version 2 and docs/plans/plan-v2.MD.

## Completed in chunk 3

- Recipe editor and saved collection with quantified ingredients, preparation states, shared components, instructions, yields, cuisine, dish identity, equipment and effort metadata.
- PostgreSQL migration 003, household row policies, immutable recipe revisions and reviewed source-food cache; stale writes use the existing household version.
- Nine source-backed USDA records with retained responses, source IDs, URLs, dates and hashes. Offline matching normalizes names/aliases and retains ambiguous raw/cooked choices for review.
- Optional fixed-host USDA search/detail adapter using a backend-only environment key. No personal-key live flow has been verified; offline records and parser fixtures work without a key.
- Whole-recipe, reference-serving, measured-yield gram and shared-component portion calculations. Unknown quantities/nutrients remain null with separately labeled known subtotals.
- Pure calculation and menu validation tool facades for milestone 3: recipe revision/coverage/uniqueness, portion conservation, reviewed restriction screening, daily target differences, stock shortfalls and qualitative effort recommendations.
- UI tests for save/edit/reload and PostgreSQL tests for revision immutability, source snapshot stability, household isolation and stale writes. Calculation fixtures independently check totals, full-week contracts and missing-data behavior.

Saved recipes do not replace the existing weekly-menu preview yet. Actual agent planning, child food-variety guidance, stock normalization review, recipe web extraction and durable feedback remain in their respective later milestones.

## Completed in chunk 2

- PostgreSQL schema migrations, checksum tracking, repeatable migration execution and administrative household/editor provisioning.
- Durable member profiles, optional manually entered adult/child targets, age groups, dislikes and restrictions.
- Durable shared cuisines and cooking preferences. New households have no assumed members, targets, stock or cooking effort.
- Durable fridge/pantry/freezer stock with supported units, availability states and unknown quantities for untracked staples.
- Add/edit profile and stock forms connected to repositories; records survive fresh Streamlit browser sessions.
- Household-scoped queries and PostgreSQL row policies that check editor membership. Runtime rejects administrative database roles.
- Atomic stock replacement and version checks so stale sessions cannot overwrite newer edits.
- Access checked on each application rerun, including after editor access is revoked. Saved-record reload clears stale form values.
- One local editor behind a loopback listener. Optional OIDC wiring requires provider configuration and provisioned editor membership; a real provider login is not yet verified.
- Private PostgreSQL setup/start/stop/status commands. Docker setup and integration tests run successfully here. Native startup is offered for other environments but could not be exercised because this workspace blocks native shared-memory allocation.
- Sample receipt confirmation uses isolated session-only preview stock in persistent households, with visible confirmation and duplicate prevention. It cannot mutate real inventory. Menu-preview resets retain saved household records.

## Cooking preferences revision — plan version 2

- Replaced minute-budget forms with usual cooking effort and weekly meal-prep preference; added recurring busier weekdays.
- Saved all three inputs through version-checked PostgreSQL transactions. New choices remain unset until entered.
- Added migration 002 without changing migration 001; retained historical minute values without assuming an effort preference.
- Removed estimated cooking time as a mandatory preview check. Week view displays busy-day preferences and explicitly states that sample menus have not adapted to them.
- Updated future planner instructions to favor fewer steps and less hands-on work on busier days, with effort feedback planned for later learning.
- Fixed read-only busy-day checkboxes in the week overview: they are editable with an explicit Save busier days action, persist across sessions, and synchronize with Household settings. Meal selections and locks remain unchanged.
- Archived plan version 2. Phase 2 includes Put and forget recipes, Instant Pot support and separately verified overnight suitability.

Equipment and qualitative effort can now be entered per recipe. Household equipment availability, personalized effort learning and actual preference-aware planning are still pending.

## Previously completed: UI prototype v0.1

- Five pages: weekly menu, groceries/stock, categorized recipes, household profiles and history.
- Seven days of breakfast, lunch, dinner and snacks, with shared dishes for one cook.
- Day/week views, portion controls, swaps, locks and sample draft regeneration.
- Separate sample receipt review and duplicate-confirmation prevention in preview mode.
- Checks for all 28 slots and distinct sample dishes. Sample cooking times remain approximate guidance; the former mandatory time-budget check was removed in version 2.
- Finalized sample-menu snapshots unaffected by later edits, within the browser session.
- Sample preparation, freezer and shopping suggestions, with pending quantities labeled.
- Agent request/result contracts, planner instructions and tool checklist.
- Version 1 handoff and identical archive, preserving all four Mermaid diagrams.
- Seven original screenshots in docs/screenshots/.

## Verification

Tested with Python 3.12, Streamlit 1.65.0 and real PostgreSQL 17. The full suite passes **59 tests**, including new-session profile/preference/stock persistence, household isolation through repositories and raw SQL, forged household access, access revocation, blocked self-provisioning, unsafe role rejection, stale saves, transaction rollback, unknown quantities, all five pages with an empty persistent household and the existing preview flows.

```sh
python -m database.local setup
python -m database.test
```

The runner creates a separate test database and removes it afterward. Application household records are not test fixtures. Basic unittest discovery skips integration cases unless both test database URLs are configured.

## MVP milestones — same numbering as plan.MD

| Milestone | Status and remaining work |
| --- | --- |
| 1 Household records | Complete for one local editor: PostgreSQL migrations, editor scoping, profiles, shared settings and manual stock. Remote identity-provider setup and verification remain deployment work. |
| 2 Recipes and calculations | Complete foundation: versioned recipes, ingredient normalization, reviewed USDA matching, yield/portion arithmetic and deterministic candidate validation. Known fixtures reproduce totals and expose unknowns. See docs/recipes-and-nutrition.md for boundaries. |
| 3 Planning loop | Next: background worker, snapshots, tools, bounded evaluator/optimizer revisions and checked seven-day drafts. The illustrative loop from chat is not installed. |
| 4 Receipt and discovery inputs | Pending: editable extraction, normalized review, durable duplicate handling, purchase confirmation, discovery/import and provenance. |
| 5 Weekly use | Pending: recalculating swaps/locks, prep/shopping/freezer tasks, durable recipe/menu snapshots, reservations, cooking/skip events and feedback. |
| 6 MVP verification | Pending: full end-to-end acceptance scenarios, deployment configuration and integration checks. |

The app now stores household inputs, reviewed source-food cache entries and immutable recipe revisions. Weekly menus, sample menu ratings and preview history remain session-based samples. There is no AI planner or receipt extraction yet. Recipe/portion arithmetic and pure candidate checks are implemented; the sample week does not use them. Child balanced-food guidance and normalized stock reconciliation remain explicit missing-data boundaries for the upcoming planning runtime.
