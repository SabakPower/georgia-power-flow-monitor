"""Electricity Balance page for the Georgia Power Flow Monitor dashboard.

Shows ESCO's monthly electricity balance for Georgia: generation by source,
consumption and cross-border flows, one selected year at a time. All values are
in GWh (1 GWh = 1 million kWh).

Layout follows the dashboard's house style: page title, one-line intro, section
sub-headings, bordered cards, a caption under every chart and one data-notes
expander at the bottom.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

BASE_DIR: Path = Path(__file__).resolve().parents[2]
DATA_FILE: Path = BASE_DIR / "data" / "processed" / "esco" / "electricity_balance_monthly_clean.csv"

# Largest accepted difference between reported net imports and imports minus exports (GWh).
NET_IMPORT_TOLERANCE_GWH: float = 0.05
MONTHS_PER_YEAR: int = 12

GENERATION_SOURCE_LABELS: dict[str, str] = {
    "hydro_mln_kwh": "Hydro",
    "thermal_mln_kwh": "Thermal",
    "wind_mln_kwh": "Wind",
    "other_generation_mln_kwh": "Other",
}

logger: logging.Logger = logging.getLogger(__name__)


@st.cache_data
def load_data(path_str: str) -> pd.DataFrame:
    """Load the processed ESCO electricity balance.

    Args:
        path_str: Path to the processed CSV, as a string (hashable for the cache).

    Returns:
        DataFrame with a parsed date column and text columns as object dtype.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file cannot be read or has no date column.
    """
    path = Path(path_str)
    try:
        balance_df = pd.read_csv(path)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Data file not found: {path.name}") from exc
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise ValueError(f"Could not read {path.name}: {exc}") from exc
    if "date" not in balance_df.columns:
        raise ValueError(f"{path.name} has no date column")

    balance_df["date"] = pd.to_datetime(balance_df["date"])
    # pandas 3's default string dtype crashes st.dataframe's Arrow serialisation
    # (streamlit/streamlit#14609), so text columns are converted to object dtype.
    for column in balance_df.select_dtypes(include=["string", "object"]).columns:
        balance_df[column] = balance_df[column].astype(object)
    return balance_df


def calculate_share_pct(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Calculate a percentage share per row, treating a zero denominator as 0%.

    Args:
        numerator: Part values.
        denominator: Total values.

    Returns:
        Shares in percent, rounded to 2 decimals.
    """
    safe_denominator = denominator.where(denominator != 0)
    return numerator.div(safe_denominator).mul(100).fillna(0).round(2)


def calculate_scalar_pct(numerator: float, denominator: float) -> float:
    """Calculate a single percentage, treating a zero or missing denominator as 0%.

    Args:
        numerator: Part value.
        denominator: Total value.

    Returns:
        Percentage rounded to 1 decimal.
    """
    if denominator == 0 or pd.isna(denominator):
        return 0.0
    return round(numerator / denominator * 100, 1)


def format_month(date_value: pd.Timestamp) -> str:
    """Format a date as short month and year, e.g. "Jun 2025".

    Args:
        date_value: Date to format.

    Returns:
        Month abbreviation and year.
    """
    return pd.to_datetime(date_value).strftime("%b %Y")


def resolve_net_imports(year_df: pd.DataFrame) -> tuple[pd.Series, float]:
    """Net imports per month: the reported column if it matches imports minus exports.

    Args:
        year_df: Balance rows for one year.

    Returns:
        Tuple of (net imports in GWh, largest difference between reported and
        calculated net imports in GWh; NaN if the reported column is absent).
    """
    calculated = year_df["import_mln_kwh"] - year_df["export_mln_kwh"]
    if "net_imports_mln_kwh" not in year_df.columns:
        return calculated, float("nan")
    reported = year_df["net_imports_mln_kwh"]
    max_difference = float((calculated - reported).abs().max())
    return (reported if max_difference <= NET_IMPORT_TOLERANCE_GWH else calculated), max_difference


def render_system_overview(year_df: pd.DataFrame) -> None:
    """Render the six headline cards for the selected year.

    Args:
        year_df: Balance rows for one year.
    """
    st.subheader("System overview")

    total_generation = year_df["generation_mln_kwh"].sum()
    total_consumption = year_df["total_consumption_mln_kwh"].sum()
    total_imports = year_df["import_mln_kwh"].sum()
    total_exports = year_df["export_mln_kwh"].sum()
    coverage_pct = calculate_scalar_pct(total_generation, total_consumption)

    top_left, top_middle, top_right = st.columns(3)
    top_left.metric("Total generation", f"{total_generation:,.0f} GWh", border=True)
    top_middle.metric("Total consumption", f"{total_consumption:,.0f} GWh", border=True)
    top_right.metric(
        "Domestic generation coverage",
        f"{coverage_pct:.1f}%",
        border=True,
        help="Total domestic generation divided by total consumption in the selected year.",
    )

    bottom_left, bottom_middle, bottom_right = st.columns(3)
    bottom_left.metric("Imports", f"{total_imports:,.0f} GWh", border=True)
    bottom_middle.metric("Exports", f"{total_exports:,.0f} GWh", border=True)
    bottom_right.metric("Net imports", f"{total_imports - total_exports:,.0f} GWh", border=True)


def render_demand_and_supply(year_df: pd.DataFrame) -> None:
    """Render generation against consumption, and the monthly domestic generation gap.

    Args:
        year_df: Balance rows for one year.
    """
    st.subheader("Demand and domestic supply")

    generation_consumption = year_df[["date", "generation_mln_kwh", "total_consumption_mln_kwh"]].rename(
        columns={"generation_mln_kwh": "Total generation", "total_consumption_mln_kwh": "Total consumption"}
    )
    generation_consumption["Generation balance"] = (
        generation_consumption["Total generation"] - generation_consumption["Total consumption"]
    )

    figure = px.line(
        generation_consumption,
        x="date",
        y=["Total generation", "Total consumption"],
        markers=True,
        labels={"date": "Month", "value": "GWh", "variable": "Indicator"},
        title="Total Generation vs Total Consumption, GWh",
    )
    figure.update_yaxes(title_text="GWh")
    figure.update_xaxes(title_text="Month")
    st.plotly_chart(figure, width="stretch")
    st.caption("Monthly totals from the ESCO electricity balance.")

    figure = px.bar(
        generation_consumption,
        x="date",
        y="Generation balance",
        labels={"date": "Month", "Generation balance": "GWh"},
        title="Domestic Generation Gap, GWh",
    )
    figure.update_yaxes(title_text="GWh")
    figure.update_xaxes(title_text="Month")
    st.plotly_chart(figure, width="stretch")
    st.caption(
        "Generation minus consumption. Positive: domestic generation exceeded consumption. "
        "Negative: consumption exceeded domestic generation. This is a domestic generation gap, "
        "not the full cross-border balance."
    )


def build_generation_shares(year_df: pd.DataFrame) -> pd.DataFrame:
    """Monthly generation shares: hydro vs non-hydro, and the split within non-hydro.

    Args:
        year_df: Balance rows for one year.

    Returns:
        DataFrame with date and share columns Hydro, Non-hydro, Thermal, Wind and Other.
    """
    shares = year_df[["date", *GENERATION_SOURCE_LABELS]].copy()
    non_hydro = shares["thermal_mln_kwh"] + shares["wind_mln_kwh"] + shares["other_generation_mln_kwh"]
    total = shares["hydro_mln_kwh"] + non_hydro

    shares["Hydro"] = calculate_share_pct(shares["hydro_mln_kwh"], total)
    shares["Non-hydro"] = calculate_share_pct(non_hydro, total)
    shares["Thermal"] = calculate_share_pct(shares["thermal_mln_kwh"], non_hydro)
    shares["Wind"] = calculate_share_pct(shares["wind_mln_kwh"], non_hydro)
    shares["Other"] = calculate_share_pct(shares["other_generation_mln_kwh"], non_hydro)
    return shares


def build_share_area_chart(shares: pd.DataFrame, columns: list[str], axis_title: str, title: str) -> go.Figure:
    """Stacked area chart of percentage shares on a 0-100% axis.

    Args:
        shares: Output of build_generation_shares.
        columns: Share columns to plot.
        axis_title: Y-axis title.
        title: Chart title.

    Returns:
        Plotly figure.
    """
    long_df = shares[["date", *columns]].melt(id_vars="date", var_name="Generation source", value_name="Share")
    figure = px.area(
        long_df,
        x="date",
        y="Share",
        color="Generation source",
        labels={"date": "Month", "Share": axis_title},
        title=title,
    )
    figure.update_yaxes(title_text=axis_title, range=[0, 100], ticksuffix="%")
    figure.update_xaxes(title_text="Month")
    return figure


def render_generation_structure(year_df: pd.DataFrame) -> None:
    """Render generation by source, hydro dependence and the non-hydro breakdown.

    Args:
        year_df: Balance rows for one year.
    """
    st.subheader("Generation structure")

    st.markdown("#### Generation by source")
    mix_long = year_df[["date", *GENERATION_SOURCE_LABELS]].melt(
        id_vars="date", var_name="generation_source", value_name="gwh"
    )
    mix_long["generation_source"] = mix_long["generation_source"].replace(GENERATION_SOURCE_LABELS)
    figure = px.area(
        mix_long,
        x="date",
        y="gwh",
        color="generation_source",
        labels={"date": "Month", "gwh": "GWh", "generation_source": "Generation source"},
        title="Monthly Generation by Source, GWh",
    )
    figure.update_yaxes(title_text="GWh")
    figure.update_xaxes(title_text="Month")
    st.plotly_chart(figure, width="stretch")
    st.caption("Other generation is the residual between total generation and the named sources.")

    shares = build_generation_shares(year_df)

    st.markdown("#### Hydro dependence")
    st.plotly_chart(
        build_share_area_chart(
            shares, ["Hydro", "Non-hydro"], "Share of domestic generation (%)", "Hydro Dependence of Domestic Generation"
        ),
        width="stretch",
    )
    st.caption("Share of domestic generation from hydro versus all non-hydro sources combined.")

    st.plotly_chart(
        build_share_area_chart(
            shares,
            ["Thermal", "Wind", "Other"],
            "Share within non-hydro generation (%)",
            "Breakdown of Non-Hydro Generation",
        ),
        width="stretch",
    )
    st.caption(
        "Composition of non-hydro generation only: percentages are within non-hydro generation, "
        "not total domestic generation."
    )


def render_cross_border(year_df: pd.DataFrame, net_imports: pd.Series) -> None:
    """Render monthly imports, exports and net imports, and the net import position.

    Args:
        year_df: Balance rows for one year.
        net_imports: Net imports per month in GWh (from resolve_net_imports).
    """
    st.subheader("Cross-border balance")

    figure = go.Figure()
    figure.add_trace(go.Bar(x=year_df["date"], y=year_df["import_mln_kwh"], name="Imports"))
    figure.add_trace(go.Bar(x=year_df["date"], y=year_df["export_mln_kwh"], name="Exports"))
    figure.add_trace(go.Scatter(x=year_df["date"], y=net_imports, name="Net imports", mode="lines+markers"))
    figure.update_layout(
        title="Monthly Cross-Border Electricity Balance, GWh",
        xaxis_title="Month",
        yaxis_title="GWh",
        barmode="group",
        legend_title="Indicator",
    )
    figure.add_hline(y=0, line_dash="dot")
    st.plotly_chart(figure, width="stretch")
    st.caption("Net imports = imports minus exports. Negative values are net export months.")

    st.markdown("#### Net import position")
    position = year_df[["date", "import_mln_kwh", "export_mln_kwh", "total_consumption_mln_kwh"]].copy()
    position["net_imports_gwh"] = net_imports.to_numpy()
    safe_consumption = position["total_consumption_mln_kwh"].where(position["total_consumption_mln_kwh"] != 0)
    position["net_import_position_pct"] = (position["net_imports_gwh"] / safe_consumption * 100).round(2)

    figure = go.Figure(
        go.Bar(
            x=position["date"],
            y=position["net_import_position_pct"],
            name="Net import position",
            customdata=position[["import_mln_kwh", "export_mln_kwh", "net_imports_gwh"]],
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
    figure.add_hline(y=0, line_dash="dot")
    figure.update_layout(
        title="Net Import Position, % of Consumption",
        xaxis_title="Month",
        yaxis_title="Net import position (% of consumption)",
        showlegend=False,
        height=430,
    )
    figure.update_yaxes(ticksuffix="%")
    st.plotly_chart(figure, width="stretch")
    st.caption(
        "Net imports divided by total consumption. Positive: net importer month. "
        "Negative: net exporter month."
    )


def render_insight(column, label: str, value: str, month: pd.Timestamp) -> None:
    """Render one key-insight card: the value, with its month in the grey line below.

    Args:
        column: Streamlit column to render into.
        label: Card label.
        value: Formatted value.
        month: Month the value belongs to.
    """
    column.metric(label, value, delta=format_month(month), delta_color="off", delta_arrow="off", border=True)


def render_key_insights(year_df: pd.DataFrame, net_imports: pd.Series) -> None:
    """Render the monthly extremes of the selected year as cards.

    Args:
        year_df: Balance rows for one year.
        net_imports: Net imports per month in GWh (from resolve_net_imports).
    """
    st.subheader("Key system insights")
    if year_df.empty:
        st.warning("No data available for the selected year.")
        return

    insight_df = year_df.copy()
    insight_df["net_imports_gwh"] = net_imports.to_numpy()
    insight_df["coverage_pct"] = calculate_share_pct(
        insight_df["generation_mln_kwh"], insight_df["total_consumption_mln_kwh"]
    )
    insight_df["hydro_pct"] = calculate_share_pct(insight_df["hydro_mln_kwh"], insight_df["generation_mln_kwh"])
    insight_df["thermal_pct"] = calculate_share_pct(insight_df["thermal_mln_kwh"], insight_df["generation_mln_kwh"])

    def row_at(column_name: str, highest: bool) -> pd.Series:
        index = insight_df[column_name].idxmax() if highest else insight_df[column_name].idxmin()
        return insight_df.loc[index]

    highest_consumption = row_at("total_consumption_mln_kwh", True)
    highest_generation = row_at("generation_mln_kwh", True)
    lowest_coverage = row_at("coverage_pct", False)
    strongest_import = row_at("net_imports_gwh", True)
    strongest_export = row_at("net_imports_gwh", False)
    highest_hydro = row_at("hydro_pct", True)
    highest_thermal = row_at("thermal_pct", True)

    first, second, third = st.columns(3)
    render_insight(first, "Highest consumption", f"{highest_consumption['total_consumption_mln_kwh']:,.0f} GWh",
                   highest_consumption["date"])
    render_insight(second, "Highest generation", f"{highest_generation['generation_mln_kwh']:,.0f} GWh",
                   highest_generation["date"])
    render_insight(third, "Lowest domestic coverage", f"{lowest_coverage['coverage_pct']:.1f}%",
                   lowest_coverage["date"])

    first, second, third = st.columns(3)
    render_insight(first, "Strongest net import", f"{strongest_import['net_imports_gwh']:,.0f} GWh",
                   strongest_import["date"])
    render_insight(second, "Strongest net export", f"{abs(strongest_export['net_imports_gwh']):,.0f} GWh",
                   strongest_export["date"])
    render_insight(third, "Highest hydro share", f"{highest_hydro['hydro_pct']:.1f}%", highest_hydro["date"])

    first, _, _ = st.columns(3)
    render_insight(first, "Highest thermal share", f"{highest_thermal['thermal_pct']:.1f}%", highest_thermal["date"])
    st.caption("Each card shows the most extreme month of the selected year; the month is in the grey line.")


def render_data_notes(year_df: pd.DataFrame, selected_year: int, net_import_difference: float) -> None:
    """Render the data notes with the checks actually run on the selected year.

    Args:
        year_df: Balance rows for one year.
        selected_year: Year shown on the page.
        net_import_difference: Largest gap between reported and calculated net imports (GWh).
    """
    months_present = len(year_df)
    empty_values = int(year_df.isna().sum().sum())
    latest_month = format_month(year_df["date"].max()) if months_present else "n/a"
    if pd.isna(net_import_difference):
        net_import_note = "the file has no reported net imports column, so imports minus exports is used"
    elif net_import_difference <= NET_IMPORT_TOLERANCE_GWH:
        net_import_note = (
            f"reported net imports match imports minus exports (largest difference "
            f"{net_import_difference:.2f} GWh)"
        )
    else:
        net_import_note = (
            f"reported net imports differ from imports minus exports by up to {net_import_difference:.2f} GWh, "
            "so imports minus exports is used instead"
        )

    checks_passed = (
        months_present == MONTHS_PER_YEAR
        and empty_values == 0
        and (pd.isna(net_import_difference) or net_import_difference <= NET_IMPORT_TOLERANCE_GWH)
    )
    if not checks_passed:
        st.warning(f"Data checks for {selected_year} found an issue; see the data notes below.")

    with st.expander("Data notes"):
        st.markdown(
            f"""
- **Source.** ESCO electricity balance, monthly, entered manually from ESCO's published balances.
- **Checks run on {selected_year}.** {months_present} of {MONTHS_PER_YEAR} months present (latest:
  {latest_month}); {empty_values} empty values; {net_import_note}. These checks cover completeness
  and internal consistency only, not the accuracy of ESCO's published figures.
- **Units.** GWh throughout (1 GWh = 1 million kWh).
- **Other generation** is the residual between total generation and the named sources.
- **Domestic generation coverage** is total generation divided by total consumption.
"""
        )
    with st.expander("Data table"):
        st.dataframe(year_df, width="stretch")


def main() -> None:
    """Render the Electricity Balance page."""
    st.title("Electricity Balance")
    st.write("Georgia's monthly electricity balance: generation by source, consumption and cross-border flows.")

    try:
        balance_df = load_data(str(DATA_FILE))
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Electricity balance could not be loaded: %s", exc)
        st.error(f"Electricity balance data could not be loaded: {exc}")
        st.stop()

    start_year, end_year = int(balance_df["year"].min()), int(balance_df["year"].max())
    st.caption(f"Source: ESCO electricity balance, {start_year}–{end_year}, monthly. Values in GWh.")

    available_years = sorted(balance_df["year"].unique(), reverse=True)
    selected_year = int(st.selectbox("Year", available_years, index=0, key="electricity_balance_year"))
    year_df = balance_df[balance_df["year"] == selected_year].copy()
    net_imports, net_import_difference = resolve_net_imports(year_df)

    render_system_overview(year_df)
    render_demand_and_supply(year_df)
    render_generation_structure(year_df)
    render_cross_border(year_df, net_imports)
    render_key_insights(year_df, net_imports)
    render_data_notes(year_df, selected_year, net_import_difference)


main()