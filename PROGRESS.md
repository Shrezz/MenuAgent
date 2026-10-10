# MenuAgent implementation progress

Updated: October 9, 2026

## Current milestone: Automatic planning and recipe discovery v0.5

Implementation chunk 5 adds the milestone 3 planning foundation and the milestone 4 web-discovery foundation. Chunk 4 delivered the receipt portion of milestone 4 ahead of the worker, at the user's request. Implementation chunk 3 completed: the recipe library and calculation foundation, corresponding to **milestone 2: Recipes and calculations** in plan.MD. Chunk 2 completed household/database persistence (milestone 1). The UI prototype was implementation chunk 1; it preceded the plan's numbered backend milestones.

The original remaining-work list in this file used different numbering. The table below now follows plan.MD exactly. Receipt extraction belongs to milestone 4; recipes and calculations belong to milestone 2. Archived version 1 remains unchanged. The agreed cooking-preference revision is recorded in plan.MD version 2 and docs/plans/plan-v2.MD.

## Completed in chunk 5

- PostgreSQL migration 005: durable job states/progress, one-transaction input snapshots, request idempotency and immutable menu candidates with repository-recomputed reports.
- Local background worker, cancellation, stale-input protection, queued-work resumption, interrupted-job detection and an independent local worker command.
- Application-controlled evaluator/optimizer workflow: complete initial week, local-model recipe/portion proposals, deterministic nutrition and whole-week checks, three menu revisions and best-candidate retention.
- Explicit budgets: 11 model calls, 40 tool steps, six external source fetches and a 600-second elapsed budget checked between steps. At most two repair calls per recipe category; request timeouts remain bounded.
- Real receipt confirmation can queue automatic planning for the selected week; sample receipts cannot. Queue failure is reported after preserving purchase confirmation.
- Weekly results UI with live progress, 28 shared meal slots, proposed adult/entered-target servings, source-backed nutrition where known, target differences, whole-week ingredients, review links and tool trace. Durable drafts appear in History.
- South Indian vegetarian discovery through Dassana’s live recipe collection, Recipe JSON-LD imports, retained links/hashes/original amounts, allowed-host redirects and bounded parsing. Recipe imports and model proposals enter review rather than the saved verified library automatically.
- Model recipe proposals have no fabricated web URL or nutrient values. Prior unreviewed proposals can be reused for the same week; saving a reviewed recipe takes precedence. Unknown source matches, quantities and child portions remain readiness issues.
- Real Gemma runs exposed incomplete recipe counts, reused dishes and a truncated revision. Explicit ideas, bounded repairs, persisted partial proposals and the calculated baseline make these cases recoverable.
- A real local run produced a saved 28-meal household draft with no required coverage/duplicate violations. Its 28 new/imported recipes remain needs_input pending quantity/dietary/nutrient review.
- Twenty-six additional tests cover model/optimizer failure, known nutrition, execution limits, stock uncertainty, recipe review, cancellation, immutable records, report recomputation, stale inputs, household isolation and UI flows.

See docs/automatic-planning.md. Finalization, actual-menu swaps/locks, reservations, cooking outcomes, detailed prep/freezer tasks and source-backed child guidance remain later work. Archived plans remain unchanged.

## Completed in chunk 4

- Local Ollama vision adapter using the already installed Gemma 4 E2B model, structured JSON output, finite request limits, input-image validation, EXIF handling and sanitized failures. No API key or additional model download required.
- Real uploaded-receipt flow: explicit Read action, original text/notes, editable ingredients/quantities/units/locations and explicit confirmation. Reading does not update stock.
- PostgreSQL migration 004 retaining original images, immutable extraction/model provenance and reviewed confirmation records under household row policies.
- Duplicate protection for identical image bytes across browser sessions. Purchase merging, confirmation and household version advance occur in one transaction. Stale sessions and failed writes leave stock and confirmation unchanged.
- Unknown quantities stay unknown; package counts are not silently converted to grams. Same name/location/unit rows merge; broader synonym/source normalization remains pending.
- Fifteen additional tests for validation, local-only transport, model failures, corrected UI confirmation, new-session duplicate handling, immutable provenance, isolation, stale saves and rollback.
- Real local Gemma call on a synthetic receipt: weights/counts/multiplied package size parsed, price-only quantity left blank and non-food item excluded after prompt refinement. The first prompt included that item; no real-receipt accuracy benchmark has been performed.

See docs/receipts-and-ollama.md. Different photos/crops of the same receipt are not yet deduplicated. Synchronous extraction uses a spinner; queued planning and recipe discovery were added in chunk 5. Archived plans remain unchanged.

## Completed in chunk 3

- Recipe editor and saved collection with quantified ingredients, preparation states, shared components, instructions, yields, cuisine, dish identity, equipment and effort metadata.
- PostgreSQL migration 003, household row policies, immutable recipe revisions and reviewed source-food cache; stale writes use the existing household version.
- Nine source-backed USDA records with retained responses, source IDs, URLs, dates and hashes. Offline matching normalizes names/aliases and retains ambiguous raw/cooked choices for review.
- Optional fixed-host USDA search/detail adapter using a backend-only environment key. No personal-key live flow has been verified; offline records and parser fixtures work without a key.
- Whole-recipe, reference-serving, measured-yield gram and shared-component portion calculations. Unknown quantities/nutrients remain null with separately labeled known subtotals.
- Pure calculation and menu validation tool facades for milestone 3: recipe revision/coverage/uniqueness, portion conservation, reviewed restriction screening, daily target differences, stock shortfalls and qualitative effort recommendations.
- UI tests for save/edit/reload and PostgreSQL tests for revision immutability, source snapshot stability, household isolation and stale writes. Calculation fixtures independently check totals, full-week contracts and missing-data behavior.

Saved recipes do not replace the separate sample-menu preview. Automatic planning, stock-state review and publisher recipe imports were added in chunk 5; child food-variety guidance, broader normalization and durable feedback remain later work.

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

Equipment and qualitative effort can now be entered per recipe. Chunk 5 adds preference-aware automatic planning; household equipment availability and personalized effort learning remain pending.

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

Tested with Python 3.12, Streamlit 1.65.0 and real PostgreSQL 17. The full suite passes **100 tests**, including new-session profile/preference/stock persistence, household isolation through repositories and raw SQL, forged household access, access revocation, blocked self-provisioning, unsafe role rejection, stale saves, transaction rollback, unknown quantities, all five pages with an empty persistent household and the existing preview flows.

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
| 3 Planning loop | Foundation implemented: durable jobs/snapshots, local worker, application-backed tools, bounded evaluator/optimizer revisions, full-week candidates and specific unresolved issues. Ready status requires implemented mandatory checks; child guidance remains an explicit review boundary. |
| 4 Receipt and discovery inputs | Receipt foundation complete: local vision extraction, editable review, retained provenance, identical-image duplicate handling and atomic purchase confirmation. South Indian vegetarian publisher discovery/import is implemented for review. General search providers, semantic receipt identity matching and broader stock normalization remain pending. |
| 5 Weekly use | Pending: recalculating swaps/locks, prep/shopping/freezer tasks, durable recipe/menu snapshots, reservations, cooking/skip events and feedback. |
| 6 MVP verification | Pending: full end-to-end acceptance scenarios, deployment configuration and integration checks. |

The app now stores household inputs, reviewed source-food cache entries, immutable recipe revisions and automatic menu drafts. Sample menus, sample ratings and preview history remain session-based. Local Ollama receipt extraction, reviewed purchase confirmation and the planning worker are implemented. Recipe/portion arithmetic and pure candidate checks apply to automatic drafts; the sample week does not use them. Source-backed child guidance and broader stock normalization remain explicit review boundaries. Finalization and weekly cooking events are still pending.
