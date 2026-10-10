from datetime import timedelta
import streamlit as st
from application.ui.components import page_heading, service

demo = service()
page_heading("Remember what worked", "History",
             "Saved weekly versions and household feedback, ready to revisit.")
if not demo.history:
    with st.container(border=True):
        st.subheader("Your first week starts here")
        st.write("Finalize a preview from This week to see its saved version here.")
        st.caption("Preview history lasts for this session.")
    st.page_link("application/ui/pages/week.py", label="Open this week", icon=":material/calendar_month:")
for item in reversed(demo.history):
    with st.expander(f"Week of {item['week_start']:%B %d, %Y} · Revision {item['revision']}", expanded=True):
        rows = []
        for day in range(7):
            row = {"Day": (item["week_start"] + timedelta(days=day)).strftime("%a %d")}
            for slot in item["slots"]:
                if slot.day == day:
                    row[slot.meal_type] = item["recipe_names"][slot.recipe_id]
            rows.append(row)
        st.dataframe(rows, hide_index=True, width="stretch")
        st.caption("Recipe names and menu slots are preserved in this preview snapshot.")
