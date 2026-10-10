from html import escape
from hashlib import sha256
import streamlit as st
from application.config import RuntimeConfig
from application.services.demo import DemoService


def service() -> DemoService:
    try:
        config = RuntimeConfig.load()
    except (ValueError, OSError) as error:
        st.error(str(error) if isinstance(error, ValueError) else "Could not read the backend configuration.")
        st.stop()
    if config.mode == "preview":
        if "_demo_service" not in st.session_state:
            st.session_state["_demo_service"] = DemoService()
        return st.session_state["_demo_service"]

    from application.repositories.households import HouseholdRepository
    from application.services.households import HouseholdService
    from database.connection import AccessDenied, Database, EditorContext, StorageUnavailable
    if config.access_mode == "oidc":
        identity = st.user.to_dict()
        if "is_logged_in" not in identity:
            st.error("Configure Streamlit's OIDC authentication before using OIDC editor mode.")
            st.stop()
        if not identity["is_logged_in"]:
            st.info("Sign in to open your household.")
            if st.button("Sign in", type="primary"):
                st.login()
            st.stop()
        issuer, subject = identity.get("iss"), identity.get("sub")
        if not issuer or not subject:
            st.error("The identity provider must supply issuer and subject claims.")
            st.stop()
        editor_subject = f"{issuer}|{subject}"
    else:
        if st.get_option("server.address") not in ("127.0.0.1", "localhost", "::1"):
            st.error("Local editor mode requires Streamlit to bind to a loopback address. Configure OIDC before remote access.")
            st.stop()
        editor_subject = config.local_editor_subject
    context = EditorContext(config.household_id, editor_subject)
    binding = (context, sha256(config.database_url.encode()).hexdigest())
    if st.session_state.get("_storage_binding") != binding:
        # Discard app data and widgets if the authenticated household changes.
        st.session_state.clear()
        st.session_state["_storage_binding"] = binding
    try:
        if "_household_service" not in st.session_state:
            st.session_state["_household_service"] = HouseholdService(HouseholdRepository(Database(config.database_url), context))
        else:
            # Check membership on every rerun without replacing the edit version.
            st.session_state["_household_service"].repository.read()
        return st.session_state["_household_service"]
    except (AccessDenied, StorageUnavailable) as error:
        st.error(str(error))
        st.stop()


def clear_editor_widgets():
    for key in list(st.session_state):
        if key.startswith(("profile-", "add-member-", "stock-editor-", "receipt-stock-")) or key in ("edit-member-id", "portions-member-id", "inventory-editor"):
            del st.session_state[key]


def page_heading(eyebrow, title, detail):
    st.markdown(f'<div class="ma-eyebrow">{escape(eyebrow)}</div>', unsafe_allow_html=True)
    st.title(title)
    st.caption(detail)


def records(value):
    if hasattr(value, "to_dict"):
        return value.astype(object).where(value.notna(), None).to_dict("records")
    if isinstance(value, dict):
        keys = list(value)
        return [dict(zip(keys, values)) for values in zip(*(value[key] for key in keys))]
    return value


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
