import streamlit as st
from application.ui.components import inventory_columns, page_heading, records, service

demo = service()
page_heading("Start with what's available", "Groceries & stock",
             "Review purchases, check your staples, and keep freezer batches visible.")
receipt_tab, stock_tab = st.tabs(["Receipt review", "Kitchen stock"])
with receipt_tab:
    left, right = st.columns([3, 2])
    with left:
        uploaded = st.file_uploader("Grocery receipt", type=["png", "jpg", "jpeg"])
        if uploaded:
            st.image(uploaded, caption="Uploaded receipt · extraction is pending integration", width="stretch")
        else:
            with st.container(border=True):
                st.write("**Your Sunday starting point**")
                st.write("Upload a receipt, then review the ingredients and quantities before planning.")
    with right, st.container(border=True):
        st.subheader("Try the review flow")
        st.caption("Load a separate sample extraction to explore corrections and confirmation.")
        if st.button("Load sample receipt", type="primary", width="stretch"):
            st.session_state["show_sample_receipt"] = True
    if st.session_state.get("show_sample_receipt"):
        st.subheader("Review sample items")
        st.caption("These sample items are not extracted from your uploaded image.")
        with st.form("receipt-review"):
            edited = st.data_editor(demo.receipt_items, column_config=inventory_columns(),
                                    num_rows="dynamic", width="stretch", key="receipt-editor")
            confirmed = st.form_submit_button("Confirm sample purchases",
                                              disabled="sample-receipt-v1" in demo.confirmed_receipts)
        if confirmed:
            try:
                demo.confirm_sample_receipt(records(edited))
                st.rerun()
            except ValueError as error:
                st.error(str(error))
        if demo.confirmed_receipts:
            st.success("Sample purchases added to kitchen stock for this session.")
            st.caption("This sample receipt has already been confirmed once.")
with stock_tab:
    st.caption("Leave quantities blank for confirmed, untracked staples.")
    with st.form("inventory-review"):
        edited_stock = st.data_editor(demo.inventory, column_config=inventory_columns(),
                                     num_rows="dynamic", width="stretch", key="inventory-editor")
        saved = st.form_submit_button("Save stock changes", type="primary")
    if saved:
        try:
            demo.inventory = demo.clean_inventory(records(edited_stock))
            st.success("Kitchen stock updated for this session.")
        except ValueError as error:
            st.error(str(error))
    st.subheader("Freezer")
    frozen = [row for row in demo.inventory if row["Location"] == "Freezer"]
    st.dataframe(frozen, hide_index=True, width="stretch")
