from datetime import timedelta
import streamlit as st
from application.ui.components import page_heading, service

demo = service()
page_heading("Remember what worked", "History",
             "Saved weekly versions and household feedback, ready to revisit.")
if demo.persistent:
    from database.connection import StorageUnavailable
    try:
        stored = demo.menu_planner.repository.list()
        st.subheader('Saved automatic drafts')
        st.caption('Immutable recipe, portion and calculation snapshots. These are planned drafts; cooking outcomes and finalization are still pending.')
        for job in stored:
            candidate = demo.menu_planner.repository.candidate(job['id'])
            if candidate is None:
                continue
            with st.expander(f"Week of {job['week_start']:%B %d, %Y} · {job['status'].replace('_',' ')} · {job['id'][:8]}"):
                rows = []
                for day in range(7):
                    row = {'Day':(job['week_start'] + timedelta(days=day)).strftime('%A')}
                    for meal in candidate['menu']['meals']:
                        if meal['day'] == day:
                            row[meal['meal_type']] = candidate['recipes'][meal['recipe_id']]['name']
                    rows.append(row)
                st.dataframe(rows,hide_index=True,width='stretch')
                st.caption(f"Candidate {candidate['menu']['version_id']} · {len(candidate['report']['issues'])} checks or recommendations")
        st.divider()
        st.subheader('Session sample previews')
    except (ValueError,StorageUnavailable) as error:
        st.error(str(error))
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
