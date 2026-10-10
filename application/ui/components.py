from html import escape
import streamlit as st
from application.services.demo import DemoService


def service() -> DemoService:
    if "_demo_service" not in st.session_state:
        st.session_state["_demo_service"] = DemoService()
    return st.session_state["_demo_service"]


def page_heading(eyebrow, title, detail):
    st.markdown(f'<div class="ma-eyebrow">{escape(eyebrow)}</div>', unsafe_allow_html=True)
    st.title(title)
    st.caption(detail)


def records(value):
    return value.to_dict("records") if hasattr(value, "to_dict") else value


def inventory_columns():
    return {
        "Item": st.column_config.TextColumn("Ingredient", required=True),
        "Location": st.column_config.SelectboxColumn("Location", options=["Fridge", "Pantry", "Freezer"]),
        "Quantity": st.column_config.NumberColumn("Quantity", min_value=0.0),
        "Unit": st.column_config.SelectboxColumn("Unit", options=["g", "ml", "each"]),
        "Status": st.column_config.SelectboxColumn("Stock status", options=["Available", "Use soon", "Low", "Out"]),
    }


def show_preview_checks():
    checks = service().preview_checks()
    with st.expander("Preview checks", expanded=False):
        for name, passed in checks.items():
            st.write(f"{'✓' if passed else '○'} {name}")
        st.caption("Nutrition, ingredient sufficiency, and dietary checks require the next integrations.")
    return checks
