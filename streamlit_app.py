"""Run with: python -m streamlit run streamlit_app.py"""
from datetime import timedelta
import streamlit as st
from application.ui.components import clear_editor_widgets, service

st.set_page_config(page_title="MenuAgent", page_icon="🌿", layout="wide")
st.markdown(
    """
    <style>
    .ma-eyebrow {color: #65725D; font-size: .75rem; font-weight: 600;
                 letter-spacing: .12em; text-transform: uppercase; margin-top: .4rem;}
    [data-testid="stMainBlockContainer"] {max-width: 1200px; padding-top: 2.4rem;}
    [data-testid="stSidebar"] h2 {letter-spacing: -.035em;}
    h1 {letter-spacing: -.04em;}
    </style>
    """,
    unsafe_allow_html=True,
)
demo = service()
with st.sidebar:
    st.markdown("## 🌿 MenuAgent")
    st.caption("Household menu planner")
    selected_week = st.date_input("Week containing", value=demo.week_start, key="global_week")
    monday = selected_week - timedelta(days=selected_week.weekday())
    if monday != demo.week_start:
        demo.week_start = monday
        demo.revision += 1
        demo.status = "Draft preview"
    st.caption(f"{len(demo.members)} members · one shared kitchen")
pages = [
    st.Page("application/ui/pages/week.py", title="This week", icon=":material/calendar_month:", default=True),
    st.Page("application/ui/pages/groceries.py", title="Groceries & stock", icon=":material/shopping_basket:", url_path="groceries"),
    st.Page("application/ui/pages/recipes.py", title="Recipes", icon=":material/menu_book:", url_path="recipes"),
    st.Page("application/ui/pages/household.py", title="Household", icon=":material/group:", url_path="household"),
    st.Page("application/ui/pages/history.py", title="History", icon=":material/history:", url_path="history"),
]
navigation = st.navigation(pages)
with st.sidebar:
    st.divider()
    if demo.persistent:
        st.caption(demo.household_name)
        st.caption("Profiles, preferences, kitchen stock, recipes and reviewed receipts are saved. Weekly menus and history remain sample previews.")
        if st.button("Reload saved household", width="stretch"):
            try:
                demo.refresh()
                clear_editor_widgets()
                st.rerun()
            except (ValueError, RuntimeError) as error:
                st.error(str(error))
        if st.button("Reset menu preview", width="stretch"):
            st.session_state.clear()
            st.rerun()
        from application.config import RuntimeConfig
        if RuntimeConfig.load().access_mode == "oidc" and st.button("Sign out", width="stretch"):
            st.session_state.clear()
            st.logout()
    else:
        st.caption("UI preview · sample household")
        st.caption("Edits last for this browser session. Weekly menus remain sample previews.")
        if st.button("Reset sample household", width="stretch"):
            st.session_state.clear()
            st.rerun()
navigation.run()
