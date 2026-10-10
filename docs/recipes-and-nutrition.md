# Recipes and nutrition — implementation chunk 3

The Recipes page now owns a real, household-scoped library. This week still uses legacy sample records; the planning runtime and interactive whole-week calculation will connect the saved library in later milestones. No example recipes are automatically inserted into actual household data.

## Use the editor

Open Recipes → Add or edit recipe. Enter a recipe or load the original example into the editor, then explicitly save it. Ingredients carry quantities, units (g/ml/each), preparation state, a reviewed source-food match, and a named shared component. Include oils, sauces and seasonings. Missing quantities or matches can be saved as an incomplete recipe; they prevent a checked planning candidate from becoming ready.

Enter reference servings. Finished gram portions additionally need a recorded cooked yield and a note describing the measurement or assumption. Preparation steps, cuisine, finished-dish identity, equipment, qualitative effort and optional time estimates are stored. Effort is entered explicitly rather than inferred from minutes. Renamed variations should retain their finished-dish identity so duplicate checking works.

Allergen and dietary metadata are household-reviewed declarations, separate from nutrient data. FoodData Central nutrient matches do not establish allergy safety. Supported screening tags are the listed allergens plus vegetarian/vegan; an unrecognized restriction returns a review issue. No allergy or dietary check runs against the legacy sample week.

## Nutrition arithmetic

For each ingredient: nutrient contribution = ingredient grams × source amount per 100 g ÷ 100. Sources distinguish raw, cooked and as-sold states. A state mismatch is a missing-data issue; there is no implicit raw-to-cooked conversion.

Grams are used directly. Volume/count quantities require ingredient-specific grams per unit and a reviewed conversion note. There is no general conversion from ml to grams or from an item count to a weight.

Whole-recipe values sum contributions. One reference serving divides by entered recipe servings. A finished gram portion divides by the recorded finished yield. Component fractions independently scale named shared components, allowing different rice/vegetable amounts from one shared preparation. A mixed-dish portion preserves the recipe's nutrient ratios.

If any contributing ingredient is missing a quantity, match, state match or nutrient, the corresponding total is null (shown as Incomplete). Separately labeled known subtotals remain available. Missing values are never treated as zero; source-reported zero is valid.

The original example has independently checked totals: 1,034.4 kcal, 38.44 g protein, 180.01 g carbohydrates and 19.24 g fat for the entire recipe; one of four reference servings has 258.6 kcal. These are estimates for the explicit example quantities, not recommended household or child serving sizes.

## Source records

Nine USDA SR Legacy food records are bundled, retrieved October 9, 2026. The retained search responses are in integrations/data/usda_responses.json; normalized per-100g snapshots are in usda_foods.json. Tests reconstruct each snapshot from its retained response, including its SHA-256 hash. Food identifiers, preparation states, retrieval dates, source URLs and hashes accompany calculations and saved recipe revisions. USDA data are public domain. [USDA API guide](https://fdc.nal.usda.gov/api-guide/), [FoodData Central FAQ](https://fdc.nal.usda.gov/faq/).

Ingredient aliases normalize whitespace, case and punctuation. Matching can return multiple candidates, such as raw/cooked chickpeas. The user reviews the match. Reviewed source aliases supply canonical ingredient names, so garbanzo beans and chickpeas share the same requirement key while preparation states remain separate. The cache is deliberately small; unmatched ingredients remain explicit.

Optional live search/detail uses MENUAGENT_USDA_API_KEY supplied only through backend environment/secret storage. No API key is included in code or Git. The adapter calls a fixed USDA host, applies a timeout/response-size limit, and sanitizes service errors. Without a key the offline catalog works and live search shows configuration guidance. Real authenticated live lookup has not been exercised with a personal key; recorded USDA responses cover parsing tests. The public exploration key was rate limited during fixture retrieval, so the retained official search responses supply the reproducible offline fixtures.

Updating an imported source cache does not change saved recipe snapshots. The editor makes retained and newer source snapshots separately selectable. Each recipe save creates an immutable revision, protected from UPDATE/DELETE by the app role. Household versions prevent stale recipe/source saves; row policies isolate both tables.

## Calculation tools for the next chunk

agent/tools/calculations.py exposes calculate_nutrition and validate_menu without Streamlit or model dependencies. validate_menu receives an explicit candidate version, saved recipe revisions, member dictionaries, normalized inventory and settings. It returns an input fingerprint, daily totals, target deviations, shopping amounts, issues and readiness.

The menu contract is a dictionary with version_id and meals. Each meal has id, day (Monday = 0), meal_type, recipe_id, recipe_revision, batch_multiplier, optional member_ids attendance and explicit member portions. A portion has member_id and exactly one of servings, grams or component_fractions. Component fractions refer to the entire reference recipe's components; summed allocations cannot exceed the prepared multiplier. All meal slots use one shared recipe.

Validation checks seven-day meal coverage, duplicate slots and finished-dish identities, recipe revisions, quantities/nutrients, attendance and portion allocation, reviewed restriction tags, stock amounts and effort preferences. Missing information and required failures block readiness. Target deviations and involved recipes on busier days remain recommendations; estimated minutes are not a mandatory budget. Known stock shortfalls require either resolution or an explicit allow_shopping setting; unconfirmed stock remains unknown, not absent or zero. The tool does not mutate or reserve stock.

The inventory contract requires canonical_name, preparation state and grams (or null). Existing manually entered stock has not yet been reconciled with recipe states; a future snapshot adapter must expose unknowns and request review rather than assume dry rice equals cooked rice.

Numeric child targets are used only when entered. Without them, the evaluator returns child_balance_review instead of inventing targets or claiming age-appropriate coverage. A sourced child-variety/serving policy remains to be connected during planning-loop implementation. The current recipe calculator previews one portion against entered daily goals; it does not claim that one portion meets a full day.

No AI planner, background jobs, recipe web extraction, stock reservation or finalized menu persistence is implemented in this chunk. Durable recipe ratings and cooking-effort feedback remain weekly-use work. Put and forget recipes remain phase 2. Archived plans are unchanged.
