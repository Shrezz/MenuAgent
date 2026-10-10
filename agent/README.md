# Planning agent

runtime.py implements an application-controlled evaluator/optimizer workflow. A trusted PostgreSQL job supplies an immutable household snapshot; the worker retrieves saved/source recipes, requests local model proposals, builds a complete baseline and calculates/validates every revision. Models do not have arbitrary tool or inventory-write access.

state.py sets model/tool/fetch/time budgets. Three menu revisions are allowed; the best candidate is retained if a revision regresses. New recipes, missing source data, unknown child servings and changed inputs prevent an unchecked ready state. Job progress and immutable candidate reports persist in PostgreSQL.

Application-backed tools provide context/recipe retrieval, nutrition, validation and candidate storage. A dynamic tool registry remains optional future work. The existing contracts.py records remain a public boundary; the current worker stores its execution state in database records.

See docs/automatic-planning.md for source discovery, budgets, recovery, model configuration and current boundaries. Weekly finalization, reservations, swaps/locks and cooking outcomes remain later work.
