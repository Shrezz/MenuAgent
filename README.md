# MenuAgent UI Preview

An interactive Streamlit prototype for reviewing the MenuAgent MVP. The original implementation handoff is saved as plan.MD version 1 and archived in docs/plans/plan-v1.MD, including the four diagrams.

## Run locally

From this directory:

    python3 -m venv .venv
    .venv/bin/python -m pip install -r requirements.txt
    .venv/bin/python -m streamlit run streamlit_app.py

## Preview capabilities

- This week: day and week layouts, recipe swaps, locked meals, preview checks and finalization.
- Individual portions: entered adult targets, a child balanced-food mode, and tentative serving controls.
- Groceries and stock: image upload preview, a clearly separate sample receipt review, and editable stock.
- Recipes: ingredient search, cuisine and meal filters, and household ratings.
- Household: profile editing, manual targets and shared cooking preferences.
- History: session snapshots of finalized preview versions.

The demo service uses sample household records and recipes. Changes last for the browser session. Recipe quantities, calculated nutrition, durable PostgreSQL persistence, receipt OCR, web recipe import and the real planning agent are the next implementation milestones. Uploaded images are displayed locally; sample receipt items are independent of the image.

The prototype checks meal coverage, sample recipe uniqueness and daily sample active time. The full dietary, inventory and nutrition validators remain in the version 1 plan.

## Project documentation

- PROGRESS.md: completed prototype work, verification and remaining MVP milestones.
- plan.MD: version 1 product baseline and diagrams.
- docs/directory-structure.md: current application and agent layout, with planned modules identified.
- docs/framework-options.md: Streamlit recommendation and alternatives.
- docs/plans/: archived plan versions.

## Validation

    python -m unittest discover -s tests

Verified with Python 3.12 and Streamlit 1.65.0. All five pages load in Streamlit's application test runner. Eight tests pass, covering preserved meal locks, weekly uniqueness, duplicate receipt confirmation, atomic invalid-input handling, rejected swaps, historical snapshots and profile edits across page reruns.

## UI review

Start on **This week** and explore the day layout and individual portions. Lock a meal, preview a fresh draft, then finalize a version and open **History**. In **Groceries & stock**, load the separate sample receipt, review it and confirm the purchases. Use **Household** to edit adult targets or the child's profile, and **Recipes** to browse the categorized sample collection.

Screenshots from the running prototype are saved in docs/screenshots/. The repository layout and prepared integration directories are documented in docs/directory-structure.md.
