import streamlit as st

st.set_page_config(
    page_title="Georgia Power Flow Monitor",
    layout="wide"
)

st.title("Georgia Power Flow Monitor")

st.write(
    """
    Open-source dashboard project for tracking Georgia's electricity system.

    Current phase: project setup and data source audit.
    """
)

st.subheader("Planned Dashboard Modules")

st.markdown(
    """
    - Generation
    - Consumption
    - Imports and exports
    - System balance
    - Market data
    - Renewable energy trends
    """
)

st.subheader("Current Work")

st.info("Phase 0-1: repository setup, source audit and initial data catalogue.")
