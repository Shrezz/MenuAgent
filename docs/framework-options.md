# MenuAgent framework options

Streamlit is the recommended first UI for this MVP: it supports Python forms, editable tables and multipage navigation, which fit household profiles, receipt review and menu exploration. The working prototype uses st.Page and st.navigation. [Streamlit navigation documentation](https://docs.streamlit.io/develop/api-reference/navigation/st.navigation).

| Option | Why consider it | Tradeoff for MenuAgent |
| --- | --- | --- |
| Streamlit | A short path to a Python UI around the planning and data services | Its rerun and session model needs deliberate state handling; keep durable records and agent jobs in application services |
| NiceGUI | Another Python-first option when layout and event-driven UI control become more important | A different UI model and additional design work; evaluate if Streamlit layout becomes a constraint |
| Next.js with a Python backend | A good direction for a more customized mobile and household account experience | Adds a JavaScript frontend, an API boundary and more implementation surface |

These tradeoffs are design recommendations for this project. NiceGUI's documentation describes its UI framework, while Next.js documents its page and layout structure. [NiceGUI project documentation](https://github.com/zauberzeug/nicegui), [Next.js layouts and pages](https://nextjs.org/docs/app/getting-started/layouts-and-pages).

Streamlit Session State persists values across reruns and pages within a session; reloading the tab resets the connection and associated state. The preview labels session-only saves explicitly. PostgreSQL will provide durable household records and menu history in the next milestone. [Streamlit Session State documentation](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state).

Keep UI modules thin so the Python domain, application services and planning agent can be reused if the frontend changes.
