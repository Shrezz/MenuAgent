import streamlit as st
import pandas as pd
from application.ui.components import inventory_columns, page_heading, records, service
from application.services.demo import DemoService
from application.ui.receipt_review import render_receipt_upload
from database.connection import StorageUnavailable

demo = service()
page_heading("Start with what's available", "Groceries & stock",
             "Review purchases, check your staples, and keep freezer batches visible.")
receipt_tab, stock_tab = st.tabs(["Receipt review", "Kitchen stock"])
with receipt_tab:
    left, right = st.columns([3, 2])
    with left:
        uploaded = st.file_uploader("Grocery receipt", type=["png", "jpg", "jpeg"], max_upload_size=8,
                                    help="Use a readable PNG or JPEG receipt of up to 8 MB. The model's results need your review.")
        if uploaded:
            render_receipt_upload(demo, uploaded)
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
        if demo.persistent:
            if "_receipt_sample_service" not in st.session_state:
                sample = DemoService()
                sample.inventory = []
                st.session_state["_receipt_sample_service"] = sample
            receipt_preview = st.session_state["_receipt_sample_service"]
        else:
            receipt_preview = demo
        st.subheader("Review sample items")
        st.caption("These sample items are not extracted from your uploaded image.")
        if demo.persistent:
            st.info("Try editing and confirming these items. They go into separate sample stock for this session; your saved kitchen stock stays unchanged.")
        with st.form("receipt-review"):
            edited = st.data_editor(receipt_preview.receipt_items, column_config=inventory_columns(),
                                    num_rows="dynamic", width="stretch", key="receipt-editor")
            confirmed = st.form_submit_button("Confirm sample purchases",
                                              disabled="sample-receipt-v1" in receipt_preview.confirmed_receipts)
        if confirmed:
            try:
                receipt_preview.confirm_sample_receipt(records(edited))
                st.rerun()
            except (ValueError, StorageUnavailable) as error:
                st.error(str(error))
        if receipt_preview.confirmed_receipts:
            st.success("Sample purchases confirmed in the separate sample stock preview." if demo.persistent
                       else "Sample purchases added to kitchen stock for this session.")
            st.caption("This sample receipt has already been confirmed once.")
            if demo.persistent:
                st.subheader("Sample stock preview")
                st.dataframe(receipt_preview.inventory, hide_index=True, width="stretch")
                st.caption("Session-only example. Enter actual groceries under Kitchen stock to save them.")
with stock_tab:
    st.caption("Leave quantities blank for confirmed, untracked staples.")
    with st.form("inventory-review"):
        stock_rows = pd.DataFrame(demo.inventory, columns=["Item", "Location", "Quantity", "Unit", "Status"]).astype(
            {"Item": "string", "Location": "string", "Quantity": "float64", "Unit": "string", "Status": "string"})
        edited_stock = st.data_editor(stock_rows, column_config=inventory_columns(),
                                     num_rows="dynamic", width="stretch", key="inventory-editor")
        saved = st.form_submit_button("Save stock changes", type="primary")
    if saved:
        try:
            demo.save_inventory(records(edited_stock))
            st.success("Kitchen stock saved in your household." if demo.persistent else "Kitchen stock updated for this session.")
        except (ValueError, StorageUnavailable) as error:
            st.error(str(error))
    st.subheader("Freezer")
    frozen = [row for row in demo.inventory if row["Location"] == "Freezer"]
    st.dataframe(frozen, hide_index=True, width="stretch")
