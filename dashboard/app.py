from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


BASE_DIR = Path(__file__).resolve().parents[1]

DATA_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "esco"
    / "electricity_balance_monthly_clean.csv"
)


st.set_page_config(
    page_title="Georgia Power Flow Monitor",
    layout="wide",
)


@st.cache_data
def load_data() -> pd.DataFrame:
    """Load processed ESCO electricity balance data."""
    df = pd.read_csv(DATA_FILE)
    df["date"] = pd.to_datetime(df["date"])
    return df


def calculate_share_pct(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Calculate percentage share safely, avoiding division-by-zero errors."""
    safe_denominator = denominator.where(denominator != 0)
    return numerator.div(safe_denominator).mul(100).fillna(0).round(2)


def calculate_scalar_pct(numerator: float, denominator: float) -> float:
    """Calculate a scalar percentage safely."""
    if denominator == 0 or pd.isna(denominator):
        return 0.0
    return round(numerator / denominator * 100, 1)


def format_month(date_value: pd.Timestamp) -> str:
    """Format a date as short month and year."""
    return pd.to_datetime(date_value).strftime("%b %Y")


st.title("Georgia Power Flow Monitor")

st.write(
    """
    Open-source dashboard project for tracking Georgia's electricity system.
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

available_years = sorted(df["year"].unique(), reverse=True)

selected_year = st.sidebar.selectbox(
    "Select year",
    available_years,
    index=0,
)

df_year = df[df["year"] == selected_year].copy()
coverage_start_year = int(df["year"].min())
coverage_end_year = int(df["year"].max())

st.caption(
    f"Data coverage: ESCO electricity balance, "
    f"{coverage_start_year}–{coverage_end_year}, monthly data. "
    f"Currently selected year: {selected_year}."
)

# -----------------------------
# 1. System Overview
# -----------------------------

st.subheader("System Overview")

total_generation = df_year["generation_mln_kwh"].sum()
total_consumption = df_year["total_consumption_mln_kwh"].sum()
total_imports = df_year["import_mln_kwh"].sum()
total_exports = df_year["export_mln_kwh"].sum()
net_imports = total_imports - total_exports

domestic_generation_coverage_pct = calculate_scalar_pct(
    total_generation,
    total_consumption,
)

st.caption("Unit: GWh. Note: 1 GWh = 1 million kWh.")

top_col1, top_col2, top_col3 = st.columns(3)

top_col1.metric("Total Generation", f"{total_generation:,.0f} GWh")
top_col2.metric("Total Consumption", f"{total_consumption:,.0f} GWh")
top_col3.metric(
    "Domestic Generation Coverage",
    f"{domestic_generation_coverage_pct:.1f}%",
)

bottom_col1, bottom_col2, bottom_col3 = st.columns(3)

bottom_col1.metric("Imports", f"{total_imports:,.0f} GWh")
bottom_col2.metric("Exports", f"{total_exports:,.0f} GWh")
bottom_col3.metric("Net Imports", f"{net_imports:,.0f} GWh")


# -----------------------------
# 2. Demand and Domestic Supply
# -----------------------------

st.subheader("Demand and Domestic Supply")

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
    title="Domestic Generation Gap, GWh",
)

fig_balance_gap.update_yaxes(title_text="GWh")
fig_balance_gap.update_xaxes(title_text="Month")

st.plotly_chart(fig_balance_gap, use_container_width=True)

st.caption(
    "Positive values mean domestic generation exceeded domestic consumption. "
    "Negative values mean domestic consumption exceeded domestic generation. "
    "This is a domestic generation gap, not the full cross-border electricity balance."
)


# -----------------------------
# 3. Generation Structure
# -----------------------------

st.subheader("Generation Structure")

st.markdown("### Monthly Generation by Source")

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
    title="Monthly Generation by Source, GWh",
)

fig_mix.update_yaxes(title_text="GWh")
fig_mix.update_xaxes(title_text="Month")

st.plotly_chart(fig_mix, use_container_width=True)

st.caption(
    "Unit: GWh. Note: 1 GWh = 1 million kWh. "
    "Other generation is calculated as the residual between total generation "
    "and visible generation categories."
)

st.markdown("### Hydro Dependence Analysis")

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


# -----------------------------
# 4. Cross-Border Electricity Balance
# -----------------------------

st.subheader("Cross-Border Electricity Balance")

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

st.markdown("### Net Import Position")

net_import_position_data = df_year[
    [
        "date",
        "import_mln_kwh",
        "export_mln_kwh",
        "total_consumption_mln_kwh",
    ]
].copy()

net_import_position_data["imports_gwh"] = net_import_position_data["import_mln_kwh"]
net_import_position_data["exports_gwh"] = net_import_position_data["export_mln_kwh"]

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

safe_consumption_gwh = net_import_position_data["total_consumption_mln_kwh"].where(
    net_import_position_data["total_consumption_mln_kwh"] != 0
)

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
    height=430,
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
# 5. Key System Insights
# -----------------------------

st.subheader("Key System Insights")


def render_insight_card(column, title: str, value: str, month: str) -> None:
    """Render a compact dashboard insight card."""
    with column:
        st.markdown(
            f"""
            <div style="
                padding: 1rem 1.1rem;
                border: 1px solid rgba(49, 51, 63, 0.18);
                border-radius: 0.75rem;
                background-color: rgba(250, 250, 250, 0.03);
                min-height: 120px;
            ">
                <div style="font-size: 0.95rem; font-weight: 600; margin-bottom: 0.5rem;">
                    {title}
                </div>
                <div style="font-size: 1.65rem; font-weight: 700; margin-bottom: 0.35rem;">
                    {value}
                </div>
                <div style="font-size: 0.85rem; opacity: 0.75;">
                    Month: {month}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


insight_data = df_year.copy()

insight_data["monthly_generation_coverage_pct"] = calculate_share_pct(
    insight_data["generation_mln_kwh"],
    insight_data["total_consumption_mln_kwh"],
)

insight_data["hydro_dependence_pct"] = calculate_share_pct(
    insight_data["hydro_mln_kwh"],
    insight_data["generation_mln_kwh"],
)

insight_data["thermal_backup_pct"] = calculate_share_pct(
    insight_data["thermal_mln_kwh"],
    insight_data["generation_mln_kwh"],
)

if insight_data.empty:
    st.warning("No data available for the selected year.")
else:
    highest_consumption = insight_data.loc[
        insight_data["total_consumption_mln_kwh"].idxmax()
    ]
    highest_generation = insight_data.loc[
        insight_data["generation_mln_kwh"].idxmax()
    ]
    lowest_domestic_coverage = insight_data.loc[
        insight_data["monthly_generation_coverage_pct"].idxmin()
    ]
    strongest_net_import = insight_data.loc[
        insight_data["net_imports_mln_kwh"].idxmax()
    ]
    strongest_net_export = insight_data.loc[
        insight_data["net_imports_mln_kwh"].idxmin()
    ]
    highest_hydro_dependence = insight_data.loc[
        insight_data["hydro_dependence_pct"].idxmax()
    ]
    highest_thermal_backup = insight_data.loc[
        insight_data["thermal_backup_pct"].idxmax()
    ]

    row1_col1, row1_col2, row1_col3 = st.columns(3)

    render_insight_card(
        row1_col1,
        "Highest Consumption",
        f"{highest_consumption['total_consumption_mln_kwh']:,.0f} GWh",
        format_month(highest_consumption["date"]),
    )

    render_insight_card(
        row1_col2,
        "Highest Generation",
        f"{highest_generation['generation_mln_kwh']:,.0f} GWh",
        format_month(highest_generation["date"]),
    )

    render_insight_card(
        row1_col3,
        "Lowest Domestic Coverage",
        f"{lowest_domestic_coverage['monthly_generation_coverage_pct']:.1f}%",
        format_month(lowest_domestic_coverage["date"]),
    )

    row2_col1, row2_col2, row2_col3 = st.columns(3)

    render_insight_card(
        row2_col1,
        "Strongest Net Import",
        f"{strongest_net_import['net_imports_mln_kwh']:,.0f} GWh",
        format_month(strongest_net_import["date"]),
    )

    render_insight_card(
        row2_col2,
        "Strongest Net Export",
        f"{abs(strongest_net_export['net_imports_mln_kwh']):,.0f} GWh",
        format_month(strongest_net_export["date"]),
    )

    render_insight_card(
        row2_col3,
        "Highest Hydro Dependence",
        f"{highest_hydro_dependence['hydro_dependence_pct']:.1f}%",
        format_month(highest_hydro_dependence["date"]),
    )

    row3_col1, row3_col2, row3_col3 = st.columns(3)

    render_insight_card(
        row3_col1,
        "Highest Thermal Backup",
        f"{highest_thermal_backup['thermal_backup_pct']:.1f}%",
        format_month(highest_thermal_backup["date"]),
    )

# -----------------------------
# 6. Data Status
# -----------------------------

st.subheader("Data Status")

monthly_records = len(df_year)
latest_available_month = (
    format_month(df_year["date"].max()) if monthly_records > 0 else "N/A"
)
missing_values_count = int(df_year.isna().sum().sum())

status_col1, status_col2, status_col3 = st.columns(3)

status_col1.metric("Data Source", "ESCO electricity balance")
status_col2.metric("Selected Year", str(selected_year))
status_col3.metric("Monthly Records", monthly_records)

status_col4, status_col5, status_col6 = st.columns(3)

status_col4.metric("Latest Available Month", latest_available_month)
status_col5.metric("Missing Values", missing_values_count)

if missing_values_count == 0 and monthly_records > 0:
    status_col6.success("Validation Status: Passed")
else:
    status_col6.warning("Validation Status: Warning")


# -----------------------------
# 7. Processed Dataset Preview
# -----------------------------

with st.expander("Processed Dataset Preview"):
    st.dataframe(df_year, use_container_width=True)