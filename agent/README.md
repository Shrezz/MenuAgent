# MenuAgent planning component

The UI preview uses the application demo service. The real agent will run in a worker and receive a household snapshot through PlanningRequest. PlanningResult returns a checked draft, a request for input, or a terminal job state.

Implement recipe selection and bounded tool use here. Keep Streamlit imports in application/ui. Nutrition arithmetic, inventory allocation and required-rule validation belong in application/domain. The application owns finalization and actual stock changes.

The next agent modules are runtime.py, state.py, and tools/registry.py. Add them when the corresponding integrations and calculation services are implemented.
