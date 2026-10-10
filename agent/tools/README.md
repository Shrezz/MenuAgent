# Agent tool implementation

Tool contracts are listed in plan.MD. Implement small typed functions around application services and source adapters:

- parse_receipt
- get_household_profile
- get_inventory
- update_inventory
- get_menu_history
- search_recipes
- import_recipe
- save_recipe
- get_reference_guidance
- lookup_food_nutrients
- calculate_nutrition
- validate_menu
- build_prep_plan
- build_shopping_list
- save_weekly_menu

The runtime injects trusted household and snapshot context. Return structured data, issues, provenance and input versions. Write tools require idempotency and expected-version checks. Profile editing and menu finalization remain application operations.

Implemented in calculations.py: calculate_nutrition and validate_menu, backed by pure domain functions. Their explicit candidate/portion/stock contracts and current review boundaries are documented in docs/recipes-and-nutrition.md. Local receipt extraction and human purchase confirmation are now implemented in integrations/ollama.py and application/services/receipts.py; registration in the future planning runtime remains pending. Other tools remain pending.
