from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


DATA_FILE = Path("data/processed/esco/electricity_balance_monthly_clean.csv")


st.set_page_config(
    page_title="Georgia Power Flow Monitor",
    layout="wide"
)


@st.cache_data
def load_data():
    df = pd.read_csv(DATA_FILE)
    df["date"] = pd.to_datetime(df["date"])
    return df


st.title("Georgia Power Flow Monitor")

st.write(
    """
    Open-source dashboard project for tracking Georgia's electricity system.

    Current version: ESCO 2025 monthly electricity balance.
    """
)


if not DATA_FILE.exists():
    st.error(f"Data file not found: {DATA_FILE}")
    st.stop()


df = load_data()

# -----------------------------
# Sidebar
# -----------------------------

st.sidebar.header("Filters")

available_years = sorted(df["year"].unique())
selected_year = st.sidebar.selectbox("Select year", available_years)

df_year = df[df["year"] == selected_year].copy()


# -----------------------------
# Key Metrics
# -----------------------------

st.subheader("System Overview")

total_generation = df_year["generation_mln_kwh"].sum()
total_consumption = df_year["total_consumption_mln_kwh"].sum()
total_imports = df_year["import_mln_kwh"].sum()
total_exports = df_year["export_mln_kwh"].sum()
net_imports = total_imports - total_exports

col1, col2, col3, col4, col5 = st.columns(5)

col1.metric("Generation", f"{total_generation:,.0f} mln kWh")
col2.metric("Consumption", f"{total_consumption:,.0f} mln kWh")
col3.metric("Imports", f"{total_imports:,.0f} mln kWh")
col4.metric("Exports", f"{total_exports:,.0f} mln kWh")
col5.metric("Net Imports", f"{net_imports:,.0f} mln kWh")


# -----------------------------
# Monthly Generation and Consumption
# -----------------------------

st.subheader("Monthly Generation and Consumption")

fig_gen_cons = px.line(
    df_year,
    x="date",
    y=["generation_mln_kwh", "total_consumption_mln_kwh"],
    markers=True,
    labels={
        "date": "Month",
        "value": "mln kWh",
        "variable": "Indicator",
    },
    title="Generation vs Consumption",
)

st.plotly_chart(fig_gen_cons, use_container_width=True)


# -----------------------------
# Generation Mix
# -----------------------------

st.subheader("Monthly Generation Mix")

generation_mix = df_year[
    [
        "date",
        "hydro_mln_kwh",
        "thermal_mln_kwh",
        "wind_mln_kwh",
        "other_generation_mln_kwh",
    ]
].copy()

generation_mix_long = generation_mix.melt(
    id_vars="date",
    var_name="generation_source",
    value_name="mln_kwh",
)

fig_mix = px.bar(
    generation_mix_long,
    x="date",
    y="mln_kwh",
    color="generation_source",
    labels={
        "date": "Month",
        "mln_kwh": "mln kWh",
        "generation_source": "Generation source",
    },
    title="Generation Mix by Month",
)

st.plotly_chart(fig_mix, use_container_width=True)


# -----------------------------
# Import / Export Balance
# -----------------------------

st.subheader("Import and Export Balance")

fig_trade = px.bar(
    df_year,
    x="date",
    y=["import_mln_kwh", "export_mln_kwh", "net_imports_mln_kwh"],
    barmode="group",
    labels={
        "date": "Month",
        "value": "mln kWh",
        "variable": "Indicator",
    },
    title="Monthly Imports, Exports and Net Imports",
)

st.plotly_chart(fig_trade, use_container_width=True)


# -----------------------------
# Shares
# -----------------------------

st.subheader("Generation and Import Indicators")

col_a, col_b = st.columns(2)

with col_a:
    fig_shares = px.line(
        df_year,
        x="date",
        y=["hydro_share_pct", "thermal_share_pct", "wind_share_pct"],
        markers=True,
        labels={
            "date": "Month",
            "value": "%",
            "variable": "Indicator",
        },
        title="Generation Source Shares",
    )
    st.plotly_chart(fig_shares, use_container_width=True)

with col_b:
    fig_import_dependency = px.line(
        df_year,
        x="date",
        y="import_dependency_pct",
        markers=True,
        labels={
            "date": "Month",
            "import_dependency_pct": "%",
        },
        title="Import Dependency",
    )
    st.plotly_chart(fig_import_dependency, use_container_width=True)


# -----------------------------
# Raw Table
# -----------------------------

st.subheader("Processed Dataset Preview")

st.dataframe(df_year, use_container_width=True)