from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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

st.caption("Unit: GWh. Note: 1 GWh = 1 million kWh.")

top_col1, top_col2, top_col3 = st.columns(3)

top_col1.metric("Total Generation", f"{total_generation:,.0f} GWh")
top_col2.metric("Total Consumption", f"{total_consumption:,.0f} GWh")
top_col3.metric("Net Imports", f"{net_imports:,.0f} GWh")

bottom_col1, bottom_col2, bottom_col3 = st.columns(3)

bottom_col1.metric("Imports", f"{total_imports:,.0f} GWh")
bottom_col2.metric("Exports", f"{total_exports:,.0f} GWh")
bottom_col3.metric(
    "Import Dependency",
    f"{df_year['import_dependency_pct'].mean():.1f}%"
)


# -----------------------------
# Monthly Generation and Consumption
# -----------------------------

st.subheader("Monthly Generation and Consumption")

generation_consumption = df_year[
    ["date", "generation_mln_kwh", "total_consumption_mln_kwh"]
].copy()

generation_consumption = generation_consumption.rename(
    columns={
        "generation_mln_kwh": "Total Generation",
        "total_consumption_mln_kwh": "Total Consumption",
    }
)

generation_consumption["Generation Balance"] = (
    generation_consumption["Total Generation"]
    - generation_consumption["Total Consumption"]
)

fig_gen_cons = px.line(
    generation_consumption,
    x="date",
    y=["Total Generation", "Total Consumption"],
    markers=True,
    labels={
        "date": "Month",
        "value": "GWh",
        "variable": "Indicator",
    },
    title="Total Generation vs Total Consumption",
)

fig_gen_cons.update_yaxes(title_text="GWh")
fig_gen_cons.update_xaxes(title_text="Month")

st.plotly_chart(fig_gen_cons, use_container_width=True)

st.caption(
    "Unit: GWh. Note: 1 GWh = 1 million kWh. "
    "Source: ESCO electricity balance data."
)

fig_balance_gap = px.bar(
    generation_consumption,
    x="date",
    y="Generation Balance",
    labels={
        "date": "Month",
        "Generation Balance": "GWh",
    },
    title="Monthly Generation Surplus / Deficit",
)

fig_balance_gap.update_yaxes(title_text="GWh")
fig_balance_gap.update_xaxes(title_text="Month")

st.plotly_chart(fig_balance_gap, use_container_width=True)

st.caption(
    "Positive values show months where generation exceeded consumption. "
    "Negative values show months where consumption exceeded generation."
)


# -----------------------------
# Generation Mix
# -----------------------------

st.subheader("Monthly Generation Mix")

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

generation_source_labels = {
    "hydro_mln_kwh": "Hydro",
    "thermal_mln_kwh": "Thermal",
    "wind_mln_kwh": "Wind",
    "other_generation_mln_kwh": "Other",
}

generation_mix_long["generation_source"] = generation_mix_long[
    "generation_source"
].replace(generation_source_labels)

fig_mix = px.area(
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

fig_trade = go.Figure()

fig_trade.add_trace(
    go.Bar(
        x=df_year["date"],
        y=df_year["import_mln_kwh"],
        name="Imports",
    )
)

fig_trade.add_trace(
    go.Bar(
        x=df_year["date"],
        y=df_year["export_mln_kwh"],
        name="Exports",
    )
)

fig_trade.add_trace(
    go.Scatter(
        x=df_year["date"],
        y=df_year["net_imports_mln_kwh"],
        name="Net Imports",
        mode="lines+markers",
    )
)

fig_trade.update_layout(
    title="Monthly Cross-Border Electricity Balance",
    xaxis_title="Month",
    yaxis_title="GWh",
    barmode="group",
    legend_title="Indicator",
)

fig_trade.add_hline(
    y=0,
    line_dash="dot",
)

st.plotly_chart(fig_trade, use_container_width=True)

st.caption(
    "Unit: GWh. Note: 1 GWh = 1 million kWh. "
    "Net imports are calculated as imports minus exports. "
    "Negative values indicate net export months."
)

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