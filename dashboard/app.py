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

def calculate_share_pct(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Calculate percentage share safely, avoiding division-by-zero errors."""
    safe_denominator = denominator.where(denominator != 0)
    return numerator.div(safe_denominator).mul(100).fillna(0).round(2)

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
# Monthly Generation by Source
# -----------------------------

st.subheader("Monthly Generation by Source")

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
    value_name="gwh",
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
    y="gwh",
    color="generation_source",
    labels={
        "date": "Month",
        "gwh": "GWh",
        "generation_source": "Generation source",
    },
    title="Monthly Generation by Source",
)

fig_mix.update_yaxes(title_text="GWh")
fig_mix.update_xaxes(title_text="Month")

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

# -----------------------------
# Hydro Dependence Analysis
# -----------------------------

st.subheader("Hydro Dependence Analysis")

generation_share_data = df_year[
    [
        "date",
        "hydro_mln_kwh",
        "thermal_mln_kwh",
        "wind_mln_kwh",
        "other_generation_mln_kwh",
    ]
].copy()

generation_share_data["total_generation_gwh"] = (
    generation_share_data["hydro_mln_kwh"]
    + generation_share_data["thermal_mln_kwh"]
    + generation_share_data["wind_mln_kwh"]
    + generation_share_data["other_generation_mln_kwh"]
)

generation_share_data["non_hydro_generation_gwh"] = (
    generation_share_data["thermal_mln_kwh"]
    + generation_share_data["wind_mln_kwh"]
    + generation_share_data["other_generation_mln_kwh"]
)

generation_share_data["Hydro"] = calculate_share_pct(
    generation_share_data["hydro_mln_kwh"],
    generation_share_data["total_generation_gwh"],
)

generation_share_data["Non-hydro"] = calculate_share_pct(
    generation_share_data["non_hydro_generation_gwh"],
    generation_share_data["total_generation_gwh"],
)

hydro_dependence_long = generation_share_data[
    ["date", "Hydro", "Non-hydro"]
].melt(
    id_vars="date",
    var_name="Generation source",
    value_name="Share",
)

fig_hydro_dependence = px.area(
    hydro_dependence_long,
    x="date",
    y="Share",
    color="Generation source",
    labels={
        "date": "Month",
        "Share": "Share of domestic generation (%)",
        "Generation source": "Generation source",
    },
    title="Hydro Dependence of Domestic Generation",
)

fig_hydro_dependence.update_yaxes(
    title_text="Share of domestic generation (%)",
    range=[0, 100],
    ticksuffix="%",
)

fig_hydro_dependence.update_xaxes(title_text="Month")

st.plotly_chart(fig_hydro_dependence, use_container_width=True)

st.caption(
    "This chart shows how much of Georgia's domestic electricity generation comes from hydro "
    "versus all non-hydro sources combined."
)


generation_share_data["Thermal"] = calculate_share_pct(
    generation_share_data["thermal_mln_kwh"],
    generation_share_data["non_hydro_generation_gwh"],
)

generation_share_data["Wind"] = calculate_share_pct(
    generation_share_data["wind_mln_kwh"],
    generation_share_data["non_hydro_generation_gwh"],
)

generation_share_data["Other"] = calculate_share_pct(
    generation_share_data["other_generation_mln_kwh"],
    generation_share_data["non_hydro_generation_gwh"],
)

non_hydro_breakdown_long = generation_share_data[
    ["date", "Thermal", "Wind", "Other"]
].melt(
    id_vars="date",
    var_name="Generation source",
    value_name="Share",
)

fig_non_hydro_breakdown = px.area(
    non_hydro_breakdown_long,
    x="date",
    y="Share",
    color="Generation source",
    labels={
        "date": "Month",
        "Share": "Share within non-hydro generation (%)",
        "Generation source": "Generation source",
    },
    title="Breakdown of Non-Hydro Generation",
)

fig_non_hydro_breakdown.update_yaxes(
    title_text="Share within non-hydro generation (%)",
    range=[0, 100],
    ticksuffix="%",
)

fig_non_hydro_breakdown.update_xaxes(title_text="Month")

st.plotly_chart(fig_non_hydro_breakdown, use_container_width=True)

st.caption(
    "This chart excludes hydro and shows the composition of non-hydro generation only. "
    "The percentages are within non-hydro generation, not total domestic generation."
)

with col_b:
    st.subheader("Net Import Position")

    net_import_position_data = df_year[
        [
            "date",
            "import_mln_kwh",
            "export_mln_kwh",
            "total_consumption_mln_kwh",
        ]
    ].copy()

    net_import_position_data["imports_gwh"] = net_import_position_data[
        "import_mln_kwh"
    ]

    net_import_position_data["exports_gwh"] = net_import_position_data[
        "export_mln_kwh"
    ]

    calculated_net_imports_gwh = (
        net_import_position_data["imports_gwh"]
        - net_import_position_data["exports_gwh"]
    )

    if "net_imports_mln_kwh" in df_year.columns:
        reported_net_imports_gwh = df_year["net_imports_mln_kwh"]
        max_net_import_difference = (
            calculated_net_imports_gwh - reported_net_imports_gwh
        ).abs().max()

        if max_net_import_difference <= 0.05:
            net_import_position_data["net_imports_gwh"] = reported_net_imports_gwh
        else:
            net_import_position_data["net_imports_gwh"] = calculated_net_imports_gwh
    else:
        net_import_position_data["net_imports_gwh"] = calculated_net_imports_gwh

    safe_consumption_gwh = net_import_position_data[
        "total_consumption_mln_kwh"
    ].where(net_import_position_data["total_consumption_mln_kwh"] != 0)

    net_import_position_data["net_import_position_pct"] = (
        net_import_position_data["net_imports_gwh"] / safe_consumption_gwh * 100
    ).round(2)

    fig_net_import_position = go.Figure()

    fig_net_import_position.add_trace(
        go.Bar(
            x=net_import_position_data["date"],
            y=net_import_position_data["net_import_position_pct"],
            name="Net Import Position",
            customdata=net_import_position_data[
                [
                    "imports_gwh",
                    "exports_gwh",
                    "net_imports_gwh",
                ]
            ],
            hovertemplate=(
                "Month: %{x|%b %Y}<br>"
                "Imports: %{customdata[0]:,.1f} GWh<br>"
                "Exports: %{customdata[1]:,.1f} GWh<br>"
                "Net imports: %{customdata[2]:,.1f} GWh<br>"
                "Net import position: %{y:.1f}%"
                "<extra></extra>"
            ),
        )
    )

    fig_net_import_position.add_hline(
        y=0,
        line_dash="dot",
    )

    fig_net_import_position.update_layout(
        title="Net Import Position, % of Consumption",
        xaxis_title="Month",
        yaxis_title="Net import position (% of consumption)",
        showlegend=False,
    )

    fig_net_import_position.update_yaxes(
        ticksuffix="%",
    )

    st.plotly_chart(fig_net_import_position, use_container_width=True)

    st.caption(
        "Positive values indicate net importer months. Negative values indicate net exporter months. "
        "Net import position is calculated as imports minus exports, divided by total consumption. "
        "Physical electricity values are shown in GWh."
    )


# -----------------------------
# Raw Table
# -----------------------------

st.subheader("Processed Dataset Preview")

st.dataframe(df_year, use_container_width=True)