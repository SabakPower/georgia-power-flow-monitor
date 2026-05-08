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

import pandas as pd

DATA_PATH = "data/raw/esco/electricity_balance_monthly.csv"

st.divider()

st.header("ESCO Electricity Balance Dashboard")

try:
    df = pd.read_csv(DATA_PATH)

    df = df.sort_values(["year", "month_number"])

    st.sidebar.header("Filters")

    years = sorted(df["year"].unique())
    selected_year = st.sidebar.selectbox(
        "Select year",
        years,
        index=len(years) - 1
    )

    year_df = df[df["year"] == selected_year].copy()

    generation_total = year_df["generation_mln_kwh"].sum()
    import_total = year_df["import_mln_kwh"].sum()
    export_total = year_df["export_mln_kwh"].sum()
    total_consumption = year_df["total_consumption_mln_kwh"].sum()

    balance_check = (
        generation_total
        + import_total
        - export_total
        - total_consumption
    )

    st.subheader(f"Annual Overview — {selected_year}")

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("Generation", f"{generation_total:,.1f} mln kWh")
    col2.metric("Imports", f"{import_total:,.1f} mln kWh")
    col3.metric("Exports", f"{export_total:,.1f} mln kWh")
    col4.metric("Total Consumption", f"{total_consumption:,.1f} mln kWh")
    col5.metric("Balance Check", f"{balance_check:,.2f} mln kWh")

    st.caption(
        "Balance formula: Generation + Import − Export − Total Consumption. "
        "Small rounding differences are expected."
    )

    st.subheader("Monthly Generation Mix")

    generation_mix = year_df[
        [
            "month",
            "thermal_mln_kwh",
            "hydro_mln_kwh",
            "wind_mln_kwh",
            "other_generation_mln_kwh",
        ]
    ].set_index("month")

    st.bar_chart(generation_mix)

    st.subheader("Generation vs Total Consumption")

    supply_demand = year_df[
        [
            "month",
            "generation_mln_kwh",
            "total_consumption_mln_kwh",
            "supplied_to_consumers_mln_kwh",
        ]
    ].set_index("month")

    st.line_chart(supply_demand)

    st.subheader("Imports and Exports")

    trade = year_df[
        [
            "month",
            "import_mln_kwh",
            "export_mln_kwh",
        ]
    ].set_index("month")

    st.bar_chart(trade)

    st.subheader("Hydro Generation Breakdown")

    hydro_breakdown = year_df[
        [
            "month",
            "hydro_regulatory_mln_kwh",
            "hydro_seasonal_mln_kwh",
            "hydro_small_mln_kwh",
        ]
    ].set_index("month")

    st.area_chart(hydro_breakdown)

    with st.expander("Show raw ESCO data"):
        st.dataframe(year_df, use_container_width=True)

except FileNotFoundError:
    st.warning(
        "ESCO electricity balance CSV not found. "
        "Expected path: data/raw/esco/electricity_balance_monthly.csv"
    )