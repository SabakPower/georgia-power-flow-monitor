"""Balancing Supply page for the Georgia Power Flow Monitor dashboard.

Shows ESCO's seller-side balancing report: how much electricity each seller
category contributed to ESCO's balancing pool, 2022-2025. Volumes only; the page
contains no tariffs, prices, costs or buyer-side data.

The page has its own year selector, independent of the Electricity Balance
page, because it covers a different dataset (2022-2025, not 2021-2025).
"""

import streamlit as st

from supply_by_category import render_supply_by_category_section

st.title("Balancing Supply")
st.write(
    "Who supplies ESCO's balancing pool: monthly volumes by seller category, "
    "from ESCO's seller-side report."
)

render_supply_by_category_section()