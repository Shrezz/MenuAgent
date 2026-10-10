import streamlit as st
from application.ui.components import page_heading, service

demo = service()
page_heading("Familiar favorites, fresh ideas", "Recipes",
             "A categorized household collection that grows with each week.")
left, middle, right = st.columns([2, 1, 1])
query = left.text_input("Search recipes", placeholder="Ingredient or dish name")
meal_type = middle.selectbox("Meal type", ["All", "Breakfast", "Lunch", "Dinner", "Snack"])
cuisines = sorted({recipe.cuisine for recipe in demo.recipes.values()})
cuisine = right.selectbox("Cuisine", ["All"] + cuisines)
filtered = [
    recipe for recipe in demo.recipes.values()
    if (meal_type == "All" or recipe.meal_type == meal_type)
    and (cuisine == "All" or recipe.cuisine == cuisine)
    and (not query or query.casefold() in " ".join((recipe.name,) + recipe.ingredients).casefold())
]
st.caption(f"{len(filtered)} sample recipes · nutrition and quantities pending")
for start in range(0, len(filtered), 2):
    for column, recipe in zip(st.columns(2), filtered[start:start + 2]):
        with column, st.container(border=True):
            st.caption(f"{recipe.meal_type.upper()} · {recipe.cuisine}" + (" · NEW IDEA" if recipe.is_new else ""))
            st.subheader(recipe.name)
            st.caption(f"{recipe.active_minutes} min active" + (" · freezer candidate" if recipe.freezer_friendly else ""))
            with st.expander("Ingredients & household feedback"):
                st.write(", ".join(recipe.ingredients))
                st.caption("Sample recipe record. Source, quantities, yield and nutrition still need to be added.")
                rating = st.selectbox("Household rating", ["Not tried", "Liked", "Okay", "Skip next time"],
                                      index=["Not tried", "Liked", "Okay", "Skip next time"].index(demo.ratings.get(recipe.id, "Not tried")),
                                      key=f"rating-{recipe.id}")
                demo.ratings[recipe.id] = rating
if not filtered:
    st.info("No sample recipes match. Try another ingredient or cuisine.")
with st.expander("Import a recipe"):
    st.text_input("Recipe URL", placeholder="https://...")
    st.caption("Web discovery and recipe extraction are the next integration step.")
