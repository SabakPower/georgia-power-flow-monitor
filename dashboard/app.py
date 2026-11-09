"""Entry point for the Georgia Power Flow Monitor dashboard.

Sets the page configuration and defines the navigation: pages are grouped by
data source in the sidebar. Each page lives in dashboard/views/. Streamlit Cloud
deploys this file, so its path must not change.
"""

import streamlit as st

st.set_page_config(page_title="Georgia Power Flow Monitor", layout="wide")

navigation = st.navigation(
    {
        "Electricity system": [
            st.Page(
                "views/electricity_balance.py",
                title="Electricity Balance",
                icon=":material/bolt:",
                default=True,
            ),
        ],
        "ESCO balancing": [
            st.Page("views/balancing_market.py", title="Balancing Supply", icon=":material/stacked_bar_chart:"),
            st.Page("views/balancing_tariffs.py", title="Balancing Tariffs", icon=":material/payments:"),
        ],
        "Exchange": [
            st.Page("views/exchange.py", title="GENEX Day-Ahead", icon=":material/swap_horiz:"),
        ],
    }
)
navigation.run()