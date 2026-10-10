from datetime import timedelta
import streamlit as st
from application.domain.models import MEAL_TYPES
from application.ui.components import page_heading, service, show_preview_checks

demo = service()
end = demo.week_start + timedelta(days=6)
page_heading("Your kitchen, planned", "This week",
             f"{demo.week_start:%B %d}–{end:%d, %Y} · shared meals, individual portions")
left, right = st.columns([3, 1])
with left:
    st.write(f"**{demo.status}** · Revision {demo.revision}")
    st.caption("Sample menu for reviewing the experience. Nutrition has not been calculated.")
with right:
    if st.button("Preview a fresh draft", width="stretch"):
        demo.fresh_draft()
        st.rerun()

menu_tab, portions_tab, prep_tab, shopping_tab = st.tabs(["Menu", "Individual portions", "Prep & freezer", "Shopping"])
with menu_tab:
    view = st.radio("Menu layout", ["Day focus", "Week overview"], horizontal=True)
    if view == "Week overview":
        overview = [
            {"Day": (demo.week_start + timedelta(days=day)).strftime("%a %d"),
             **{slot.meal_type: demo.recipes[slot.recipe_id].name for _, slot in demo.day_slots(day)},
             "Active min": demo.active_minutes(day)}
            for day in range(7)
        ]
        st.dataframe(overview, width="stretch", hide_index=True)
    day = st.selectbox("Choose a day", list(range(7)),
                       format_func=lambda value: (demo.week_start + timedelta(days=value)).strftime("%A, %B %d"))
    budget = f"{demo.daily_minutes} min daily budget" if demo.daily_minutes is not None else "Set a daily budget in Household"
    st.caption(f"{demo.active_minutes(day)} min estimated active work · {budget}")
    pairs = demo.day_slots(day)
    for start in (0, 2):
        columns = st.columns(2)
        for column, (index, slot) in zip(columns, pairs[start:start + 2]):
            recipe = demo.recipes[slot.recipe_id]
            with column, st.container(border=True):
                st.caption(f"{slot.meal_type.upper()} · {recipe.cuisine}")
                st.subheader(recipe.name)
                st.caption(f"{recipe.active_minutes} min active · same dish for the household")
                if recipe.prep_component:
                    st.write(f"Uses prepared **{recipe.prep_component.lower()}**")
                else:
                    st.write("Simple preparation")
                slot.locked = st.checkbox("Keep this meal", value=slot.locked, key=f"lock-{index}")
                choices = demo.alternatives(index)
                ids = [item.id for item in choices]
                chosen = st.selectbox("Alternative recipe", ids, index=ids.index(slot.recipe_id),
                                      format_func=lambda recipe_id: demo.recipes[recipe_id].name,
                                      disabled=slot.locked, key=f"swap-choice-{index}")
                if st.button("Apply swap", disabled=slot.locked or chosen == slot.recipe_id,
                             key=f"swap-button-{index}", width="stretch"):
                    demo.swap(index, chosen)
                    st.rerun()
    checks = show_preview_checks()
    if st.button("Finalize preview", type="primary", disabled=not all(checks.values())):
        demo.finalize_preview()
        st.success("This preview version is saved in session history.")
        st.rerun()

with portions_tab:
    if not demo.members:
        st.info("Add household members on the Household page to review individual portions.")
    else:
        members_by_id = {item.id: item for item in demo.members}
        member_id = st.selectbox("Household member", list(members_by_id),
                                 format_func=lambda value: members_by_id[value].name, key="portions-member-id")
        member = members_by_id[member_id]
        if member.targets:
            st.caption("Entered daily targets" if demo.persistent else "Entered daily targets · sample profile")
            columns = st.columns(4)
            for column, key, label, unit in zip(columns, ["kcal", "protein", "carbs", "fat"],
                                               ["Calories", "Protein", "Carbs", "Fat"], ["kcal", "g", "g", "g"]):
                column.metric(label, f"{member.targets[key]:g} {unit}")
        else:
            st.write("**Food variety and age-appropriate servings**")
            st.caption("Child profiles use balanced-food mode unless manual targets are entered.")
        st.info("Planned totals and serving weights will appear when verified recipe quantities are added.")
        for index, slot in demo.day_slots(day):
            recipe = demo.recipes[slot.recipe_id]
            with st.container(border=True):
                st.write(f"**{slot.meal_type} · {recipe.name}**")
                if member.kind == "Child":
                    st.caption("Serving suggestion pending recipe details and the child's profile.")
                else:
                    slot.portion_shares[member.id] = st.number_input(
                        "Portion multiplier", min_value=0.25, max_value=3.0, step=0.25,
                        value=slot.portion_shares.get(member.id, 1.0),
                        key=f"portion-{member.id}-{index}",
                    )
                    st.caption("Preview control: a reference portion will come from the recipe yield.")

with prep_tab:
    st.subheader("Prepare once, use in different meals")
    st.caption("Illustrative tasks for the sample menu; estimated preparation times.")
    st.dataframe([
        {"Prepare": "Plain chickpeas", "Active min": 12, "Uses": "Lemon salad; chickpea curry"},
        {"Prepare": "Tomato-onion base", "Active min": 18, "Uses": "Dal; rajma; freeze surplus"},
        {"Prepare": "Chopped vegetables", "Active min": 10, "Uses": "Wraps; stir-fry; khichdi"},
    ], hide_index=True, width="stretch")
    batch_budget = f"{demo.batch_minutes} min available" if demo.batch_minutes is not None else "batch budget not set"
    st.write(f"**Sunday before the week begins:** 40 min sample active preparation / {batch_budget}")
    st.subheader("Freezer suggestions")
    st.write("Set aside surplus tomato-onion base for another week.")
    st.caption("Storage instructions and batch quantities will be linked to recipe details.")
    st.write("**Use soon:** spinach and yogurt")

with shopping_tab:
    st.subheader("Ingredients to review")
    st.caption("Unquantified sample suggestions. Exact shortfalls require recipe amounts and available stock.")
    st.dataframe([
        {"Ingredient": "Lemons", "For": "Chickpea salad; lemon chicken", "Quantity": "To calculate"},
        {"Ingredient": "Tortillas", "For": "Wraps; black bean tacos", "Quantity": "To calculate"},
        {"Ingredient": "Paneer", "For": "Vegetable wrap", "Quantity": "To calculate"},
    ], hide_index=True, width="stretch")
