import streamlit as st
from application.ui.components import page_heading, service

demo = service()
page_heading("One kitchen, everyone's preferences", "Household",
             "Set personal targets and shared cooking preferences.")
members_by_id = {item.id: item for item in demo.members}
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
    name = st.text_input("Name", value=member.name)
    age_groups = ["Toddler", "Preschool", "School age", "Teen"]
    age_group = st.selectbox("Age group", age_groups,
                            index=age_groups.index(member.age_group) if member.age_group in age_groups else 2,
                            disabled=kind != "Child")
    if manual:
        values = member.targets or {}
        columns = st.columns(4)
        kcal = columns[0].number_input("Calories (kcal/day)", min_value=0.0, value=values.get("kcal"), step=50.0)
        protein = columns[1].number_input("Protein (g/day)", min_value=0.0, value=values.get("protein"), step=5.0)
        carbs = columns[2].number_input("Carbs (g/day)", min_value=0.0, value=values.get("carbs"), step=5.0)
        fat = columns[3].number_input("Fat (g/day)", min_value=0.0, value=values.get("fat"), step=5.0)
    dislikes = st.text_input("Dislikes", value=member.dislikes, placeholder="Foods the household would rather avoid")
    restrictions = st.text_input("Allergies and dietary restrictions", value=member.restrictions,
                                 placeholder="Enter restrictions to carry into planning")
    submitted = st.form_submit_button("Save member profile", type="primary")
if submitted:
    if not name.strip():
        st.error("Enter a name.")
    elif manual and any(value is None or value <= 0 for value in [kcal, protein, carbs, fat]):
        st.error("Enter positive daily values for all four targets, or turn off manual targets.")
    else:
        member.name = name.strip()
        member.kind = kind
        member.age_group = age_group if kind == "Child" else ""
        member.targets = {"kcal": kcal, "protein": protein, "carbs": carbs, "fat": fat} if manual else None
        member.dislikes = dislikes
        member.restrictions = restrictions
        st.success("Member profile saved for this session.")

st.divider()
st.subheader("Shared cooking preferences")
with st.form("shared-settings"):
    chosen_cuisines = st.multiselect("Usual cuisines", ["Indian", "South Indian", "Mediterranean", "Mexican", "East Asian", "Italian", "Everyday"],
                                    default=demo.cuisines)
    left, right = st.columns(2)
    daily_minutes = left.number_input("Daily active cooking budget (min)", min_value=10, max_value=180,
                                      value=demo.daily_minutes, step=5)
    batch_minutes = right.number_input("Sunday batch preparation budget (min)", min_value=0, max_value=180,
                                       value=demo.batch_minutes, step=5)
    st.caption("One cook prepares shared meals. Individual differences use portions and easy additions.")
    shared_saved = st.form_submit_button("Save shared preferences")
if shared_saved:
    demo.cuisines = chosen_cuisines
    demo.daily_minutes = daily_minutes
    demo.batch_minutes = batch_minutes
    st.success("Shared preferences saved for this session.")
