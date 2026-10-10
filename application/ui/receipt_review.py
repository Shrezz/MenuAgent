"""Actual uploads are kept separate from the sample receipt demonstration."""
import pandas as pd
import streamlit as st

from application.domain.receipts import extraction_rows, receipt_hash
from application.ui.components import inventory_columns, records
from database.connection import StorageUnavailable
from integrations.ollama import ReceiptModelUnavailable, prepare_image


def render_receipt_upload(household, uploaded):
    if uploaded is None:
        return
    try:
        image_bytes = uploaded.getvalue()
        image_hash = receipt_hash(image_bytes)
        prepare_image(image_bytes)
        st.image(image_bytes, caption="Uploaded receipt · review required before stock changes", width="stretch")
        review = household.receipt_review
        receipt = review.find(image_hash)
        st.caption("Read with local Ollama. Default model: Gemma 4 E2B. Reading may take up to two minutes; stock changes only after confirmation.")
        if st.button("Read receipt with Ollama", type="primary", disabled=receipt is not None):
            with st.spinner("Reading the receipt on your computer…"):
                receipt = review.read(image_bytes)
        if receipt is None:
            return
        st.caption(f"Read with {receipt['model']} · {'saved in your household' if household.persistent else 'session-only preview'}")
        with st.expander("Receipt text and extraction notes"):
            st.text(receipt["extraction"]["raw_text"])
            st.dataframe([{"Receipt line": i["raw_line"], "Review note": i["note"]}
                          for i in receipt["extraction"]["items"]], hide_index=True, width="stretch")
        if receipt["confirmed_at"] is not None:
            st.success("This receipt is already confirmed. Its purchases will not be added again.")
            st.dataframe(receipt["reviewed_items"], hide_index=True, width="stretch")
            return
        st.subheader("Review your purchases")
        st.caption("Check every name, quantity, unit and storage location. Remove incorrect or non-food rows. Blank quantities stay untracked; each means a counted item or package, not a weight.")
        rows = extraction_rows(receipt["extraction"])
        if not rows:
            st.warning("No readable groceries were found. Add items below or upload a clearer image.")
        frame = pd.DataFrame(rows, columns=["Item", "Location", "Quantity", "Unit", "Status"]).astype(
            {"Item": "string", "Location": "string", "Quantity": "float64", "Unit": "string", "Status": "string"})
        with st.form("real-receipt-" + image_hash):
            edited = st.data_editor(frame, column_config=inventory_columns(), num_rows="dynamic", width="stretch",
                                    key="receipt-stock-" + image_hash)
            confirmed = st.form_submit_button("Confirm reviewed purchases", type="primary")
        if confirmed:
            review.confirm(image_hash, records(edited))
            # The kitchen editor may have been rendered before this confirmation.
            st.session_state.pop("inventory-editor", None)
            st.rerun()
    except (ValueError, StorageUnavailable, ReceiptModelUnavailable) as error:
        st.error(str(error))
