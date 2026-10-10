# Automatic planning and South Indian vegetarian discovery

## Use the feature

Under **This week**, choose the cuisine, vegetarian preference, web discovery, new recipe suggestions and extra-shopping permission, then click **Generate automatic menu**. Review stock preparation states when quantities should be allocated precisely. Jobs run outside the Streamlit page request; progress refreshes every three seconds. Page navigation does not stop the job.

Receipt confirmation now has **Plan the selected week after confirming purchases**, enabled by default for persistent households. It queues the same planner after purchases commit. This follows the sidebar's selected Monday–Sunday week; it is not a separate Sunday timer. A failed queue operation does not undo confirmed purchases and shows instructions to start planning on This week. Sample receipts never trigger real planning.

Results show a seven-day menu, individual recipe servings, calculated daily calories/macros and target differences, whole-week ingredient needs, source links, review items and agent tool steps. Generated/imported recipes can be sent to the existing recipe editor with **Review in recipe editor**. Save reviewed recipes and regenerate; snapshots from the previous job remain unchanged. History stores automatic drafts separately from session-only sample previews.

Under **Recipes → Discover online**, search the South Indian collection, select a result, open its source or import its structured recipe for review. No recipe is automatically added to the saved library.

## Application and agent loop

1. PostgreSQL stores a queued job and a single-transaction input snapshot: household version, members, preferences, confirmed stock, exact recipe revisions, recent checked planned-draft families and this week's prior unreviewed proposals.
2. The local worker claims the job once. The runtime reads snapshot context, retrieves source candidates, imports structured recipes, and asks the local model for missing recipe proposals. Prior proposals may be reused within the same week; they remain unreviewed until saved through the recipe editor.
3. Application code builds a complete baseline with distinct dishes, stock-name matches, history preferences and easy recipes on busy days. Adults without targets receive a provisional reference serving. With entered targets and known calories, initial amounts use a labeled heuristic split of the entered daily calorie target: 25% breakfast, 30% lunch, 30% dinner and 15% snacks. The app never creates numeric child targets; children without targets require serving review.
4. Code calculates and stores the initial menu/report. The model proposes revisions using the recipe catalog and evaluator feedback. Code checks each proposal again, including coverage, exact recipe revisions, shared portion amounts, restrictions, ingredient quantities, nutrition completeness and repeated finished dishes.
5. At most three menu proposals are attempted. The best candidate is retained when a revision regresses. A truncated/unavailable menu-model response retains the baseline with a visible note. A failed recipe-generation step may leave only partial proposals; the job returns missing-input or failure status instead of claiming a complete checked menu.
6. Immutable candidates and reports are stored together. The repository recomputes reports rather than trusting a supplied ready flag, prevents changes to saved recipe snapshots, and checks input versions before a job can become draft_ready.
7. The app displays draft_ready only when implemented mandatory checks pass. Missing nutrition, new recipe review, dietary review, child portions or changed inputs produce needs_input. Recommendations and adult target differences remain visible even when a draft is ready.

The loop is an application-controlled evaluator/optimizer workflow. Models propose data; they have no arbitrary tool, SQL, shell or inventory-write access. The runtime records application-backed retrieval, calculation, validation and save steps. Dynamic tool selection and a generic tool registry are not required for this first workflow.

## Local model and budgets

Planning uses the installed `gemma4:e2b` through local Ollama. Override the backend-only **MENUAGENT_PLANNING_MODEL** to compare another installed text model. The existing loopback-only transport, disabled proxies/redirects, cloud-model rejection and structured JSON contracts are reused; no API key or new model download is needed.

Each job allows at most 11 model calls, 40 tool steps, six external recipe fetches and three menu revisions, with a 600-second elapsed budget checked between steps. Recipe proposal repair allows two attempts per meal category. Model calls have a timeout capped at 120 seconds and the remaining budget; publisher fetches have a 12-second timeout and a 3 MB response limit. Model output is shape/quantity checked in code. Common South Indian families such as idli and dosa are normalized to catch renamed variants; more general semantic duplicate detection still benefits from human recipe-identity review.

Gemma's live runs exposed short recipe lists, duplicate slots and a truncated menu response. Explicit novel dish ideas, bounded repairs, persisted partial proposals and a calculated initial week make those outcomes recoverable. Tests also exercise a regressing optimizer, invalid recipe IDs and model timeout. The local model is not treated as a reliable nutrition calculator.

## Web connection and provenance

The first adapter uses [Dassana’s South Indian vegetarian collection](https://www.vegrecipesofindia.com/recipes/south-indian-recipes/). South Indian discovery reads this publisher's live collection; other keyword searches use its RSS search feed, whose ranking can be broad. This is a bounded publisher search, not a general internet search engine.

Recipe pages expose Recipe JSON-LD with ingredient text, steps, source yield and category. The adapter retains URLs and content hashes, rejects unsupported hosts/ports and cross-publisher redirects, strips markup and imposes response/structure limits. Recipe quantities written explicitly in grams can be imported; cup/spoon weights, ingredient preparation states and nutrient matches remain unverified. Original ingredient text is preserved. The existing editor supports manually reviewed conversions and USDA matches.

A model-created novel recipe has no claimed web-source URL; its provenance is the recorded model and job. Exact web imports retain their publisher URL and steps. Both are marked for review rather than automatically added as verified recipes. Website failures retain available links and visible notes; the worker can continue using saved recipes and local proposals.

## Persistence, concurrency and boundaries

Migration 005 adds household-scoped planning_jobs and insert-only menu_candidates. The app can update job status/progress but cannot rewrite snapshots or candidates. Queue keys prevent duplicate automatic requests for the same event/week/version/options. Manual regeneration creates a new job. All retrieval and writes remain scoped through the existing editor membership and PostgreSQL row policies.

The bundled worker runs one daemon thread per app process. Queued work resumes when the household opens the planning page; **python -m workers.planning --once** can process one queued local job independently. An interrupted running job becomes failed after its heartbeat is twelve minutes old, rather than silently claiming completion. Cancellation takes effect after an in-flight request returns; cancelled jobs retain already-saved candidates but cannot save subsequent revisions or become ready. Multiple production worker processes, deployment supervision and OIDC worker credentials still need deployment work.

Draft generation does not consume or reserve stock. Unknown stock grams/states remain unknown. With explicit shopping permission, the report can recommend checking stock or purchasing up to the full known requirement; that is a conservative upper bound, not an invented exact shortfall. With shopping disabled, unknown availability or shortages block readiness. Saved recipes are not modified by the planner.

New recipes have no automatically approved nutrient matches. Children without entered numeric targets have no inferred numeric portions; child serving and balanced-food guidance remain review boundaries. Finalization, real-menu swaps/locks, ingredient reservations, detailed batch/freezer schedules, food-storage guidance, cooking/skip events and ratings are later weekly-use work. The older sample preview controls affect only sample menus.

## Verification

The deterministic/real-PostgreSQL suite covers complete weeks, quantity/nutrition arithmetic, optimizer revisions, unknown stock, child review, input-version changes, immutable snapshots, report recomputation, cancellation, household isolation, receipt-triggered queuing, new-session results and web-import review. Database tests use isolated databases. Live publisher search and the Lemon Rice/Upma structured pages were also verified.

A real local Ollama run using the household's saved inputs produced a 28-meal draft with zero required coverage/duplicate violations. Its new/imported recipes remain needs_input for human recipe and nutrient review; no unsupported macro totals were fabricated. This is functional verification, not a benchmark of recipe quality or nutritional adequacy.
