# MenuAgent implementation progress

Updated: October 8, 2026

## Current milestone: UI prototype v0.1

The first interactive Streamlit prototype is complete. It uses sample household data and session-only storage so the product flows can be reviewed before implementing persistence and planning integrations.

Completed:

- Five pages: weekly menu, groceries and kitchen stock, categorized recipes, household profiles, and history.
- Seven days of breakfast, lunch, dinner, and snacks, with shared dishes for one cook.
- Day and week views, individual portion controls, recipe swaps, meal locks, and sample draft regeneration.
- Manual adult calorie and macro target editing; children default to balanced-food mode with optional manually entered targets.
- Receipt image preview, a separately labeled sample receipt review, editable stock, and purchase confirmation that prevents double counting.
- Preview checks for all 28 meal slots, distinct finished dishes, and daily sample active cooking time.
- Finalized menu snapshots that remain unchanged when the current menu is edited.
- Sample preparation, freezer, and shopping suggestions, with pending quantities labeled.
- Application/domain/UI separation, agent request/result contracts, planner instructions, and a tool implementation checklist.
- Version 1 MVP handoff in `plan.MD`, with an identical archive in `docs/plans/plan-v1.MD`; all four Mermaid diagrams are preserved.
- Seven screenshots captured from the running interface in `docs/screenshots/`.

## Verification

Verified with Python 3.12 and Streamlit 1.65.0. All five pages load in Streamlit's application test runner. Eight automated tests pass for meal locks, uniqueness, receipt confirmation, invalid-input atomicity, rejected swaps, immutable history, and member edits across reruns. Receipt confirmation and profile/menu/history screens were also reviewed in the browser.

Run the checks from the project root:

```sh
python -m unittest discover -s tests
```

## Remaining MVP milestones

1. PostgreSQL migrations and repositories for household profiles, preferences, recipe records, inventory, receipts, and menu versions.
2. Receipt extraction and normalized item review, with durable idempotent purchase confirmation.
3. Verified recipe yields and ingredient quantities, sourced nutrition data, and deterministic serving and daily nutrient calculations.
4. Full dietary, inventory, variety, and workload validation, including locked slots and easy individual additions to shared meals.
5. Recipe discovery/import and the bounded planning-agent loop, running as a background job from a household input snapshot.
6. Durable finalization, ingredient reservations, cooking/skip events, freezer batch tracking, household feedback, and weekly regeneration.

The current preview does not run an AI planner, extract uploaded receipts, calculate nutrition, or persist records across browser sessions. These remain within the version 1 MVP scope.
