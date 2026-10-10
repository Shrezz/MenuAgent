import streamlit as st
from dataclasses import replace
from application.domain.households import AGE_GROUPS, CUISINES, COOKING_EFFORTS, MEAL_PREP_PREFERENCES, WEEKDAYS
from application.ui.components import page_heading, service
from database.connection import StorageUnavailable

demo = service()
page_heading("One kitchen, everyone's preferences", "Household",
             "Set personal targets and shared cooking preferences.")
save_scope = "in your household" if demo.persistent else "for this session"
with st.expander("Add a household member", expanded=not demo.members):
    with st.form("add-member-form", clear_on_submit=True):
        new_name = st.text_input("New member name", key="add-member-name")
        new_kind = st.selectbox("New member profile mode", ["Adult", "Child"], key="add-member-kind")
        new_age = st.selectbox("New child's age group", AGE_GROUPS, index=2, key="add-member-age")
        st.caption("Daily targets are optional and can be entered after adding the member. Children start in balanced-food mode.")
        added = st.form_submit_button("Add member")
    if added:
        try:
            demo.add_member(new_name, new_kind, new_age if new_kind == "Child" else "")
            st.success(f"Member added {save_scope}.")
        except (ValueError, StorageUnavailable) as error:
            st.error(str(error))
if not demo.members:
    st.info("Add your first member above, then enter their preferences and optional targets.")
members_by_id = {item.id: item for item in demo.members}
if members_by_id:
    member_id = st.selectbox("Edit member", list(members_by_id),
                             format_func=lambda value: members_by_id[value].name, key="edit-member-id")
    member = members_by_id[member_id]
    prefix = f"profile-{member.id}"
    kind = st.selectbox("Profile mode", ["Adult", "Child"], index=0 if member.kind == "Adult" else 1,
                       key=f"{prefix}-kind")
    manual = st.checkbox("Use manually entered daily targets", value=member.targets is not None,
                         key=f"{prefix}-manual")
    if kind == "Child":
        st.caption("Default: food variety, balanced meals and age-appropriate servings.")
    with st.form(f"{prefix}-form"):
        name = st.text_input("Name", value=member.name, key=f"{prefix}-name")
        age_group = st.selectbox("Age group", AGE_GROUPS,
                                index=AGE_GROUPS.index(member.age_group) if member.age_group in AGE_GROUPS else 2,
                                disabled=kind != "Child", key=f"{prefix}-age")
        if manual:
            values = member.targets or {}
            columns = st.columns(4)
            kcal = columns[0].number_input("Calories (kcal/day)", min_value=0.0, value=values.get("kcal"), step=50.0, key=f"{prefix}-kcal")
            protein = columns[1].number_input("Protein (g/day)", min_value=0.0, value=values.get("protein"), step=5.0, key=f"{prefix}-protein")
            carbs = columns[2].number_input("Carbs (g/day)", min_value=0.0, value=values.get("carbs"), step=5.0, key=f"{prefix}-carbs")
            fat = columns[3].number_input("Fat (g/day)", min_value=0.0, value=values.get("fat"), step=5.0, key=f"{prefix}-fat")
        dislikes = st.text_input("Dislikes", value=member.dislikes, key=f"{prefix}-dislikes", placeholder="Foods the household would rather avoid")
        restrictions = st.text_input("Allergies and dietary restrictions", value=member.restrictions, key=f"{prefix}-restrictions",
                                     placeholder="Enter restrictions to carry into planning")
        submitted = st.form_submit_button("Save member profile", type="primary")
    if submitted:
        try:
            updated = replace(member, name=name, kind=kind, age_group=age_group if kind == "Child" else "",
                              targets={"kcal": kcal, "protein": protein, "carbs": carbs, "fat": fat} if manual else None,
                              dislikes=dislikes, restrictions=restrictions)
            demo.save_member(updated)
            st.success(f"Member profile saved {save_scope}.")
        except (ValueError, StorageUnavailable) as error:
            st.error(str(error))

st.divider()
st.subheader("Shared cooking preferences")
with st.form("shared-settings"):
    chosen_cuisines = st.multiselect("Usual cuisines", CUISINES,
                                    default=demo.cuisines, key="profile-shared-cuisines")
    left, right = st.columns(2)
    efforts = list(COOKING_EFFORTS)
    prep_options = list(MEAL_PREP_PREFERENCES)
    cooking_effort = left.selectbox("Usual cooking effort", efforts,
                                   index=efforts.index(demo.cooking_effort) if demo.cooking_effort else None,
                                   format_func=COOKING_EFFORTS.get, key="profile-shared-effort",
                                   placeholder="Choose what feels manageable",
                                   help="Describe the work you are comfortable with. Recipe times vary from person to person.")
    meal_prep = right.selectbox("Weekly meal-prep preference", prep_options,
                               index=prep_options.index(demo.meal_prep) if demo.meal_prep else None,
                               format_func=MEAL_PREP_PREFERENCES.get, key="profile-shared-prep",
                               placeholder="Choose a prep preference",
                               help="Preparing components ahead can make different meals easier later in the week.")
    busy_days = st.multiselect("Usually busier days", WEEKDAYS, default=demo.busy_days,
                               key="profile-shared-busy",
                               help="The planner will favor easy recipes on these days, with fewer steps and less hands-on work.")
    st.caption("One cook prepares shared meals. Individual differences use portions and easy additions.")
    st.caption("These preferences are saved for the future planner. Sample menus do not yet adapt to them.")
    shared_saved = st.form_submit_button("Save shared preferences")
if shared_saved:
    try:
        demo.save_settings(chosen_cuisines, cooking_effort, meal_prep, busy_days)
        st.success(f"Shared preferences saved {save_scope}.")
    except (ValueError, StorageUnavailable) as error:
        st.error(str(error))
