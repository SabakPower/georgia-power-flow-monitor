
"""GENEX Day-Ahead page for the Georgia Power Flow Monitor dashboard.

Shows the GENEX day-ahead exchange: cleared volume, the traded price on GENEX and
a comparison with ESCO's balancing tariff (sold), July 2024 onwards. It is a
separate market from ESCO's balancing pool and covers a different period
(2024-2026), so it has its own page.
"""

import streamlit as st

from genex_exchange import render_genex_exchange_section

st.title("GENEX Day-Ahead")
st.write(
    "Georgia's day-ahead electricity exchange: how much energy cleared each month, "
    "at what price, and how that price compares with ESCO's balancing tariff."
)
st.caption("Source: GENEX day-ahead market export and ESCO. Jul 2024 to Sep 2026, GEL.")

render_genex_exchange_section()