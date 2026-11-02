import logging

import streamlit as st

from src import auth
from src.navigation import load_navigation_pages

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

st.set_page_config(page_title="Sales Dashboard", layout="wide")

auth.require_login()

try:
    pages = load_navigation_pages()
    pages.append(st.Page("pages/reports.py", title="Reports"))
    pages.append(st.Page("pages/customers.py", title="Customers"))
    pages.append(st.Page("pages/equivalent_models.py", title="Equivalent Models"))
    navigation = st.navigation(pages, position="sidebar")
except Exception:
    st.error("Navigation settings are unavailable. Check the database connection.")
    st.stop()

navigation.run()

auth.render_profile()
