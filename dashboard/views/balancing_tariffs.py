"""Balancing electricity tariffs page for the Georgia Power Flow Monitor dashboard.

Displays the two regulated ESCO balancing electricity tariff series for
2022-2025. These are regulated ESCO settlement tariffs, NOT market prices.

The page shows and summarises the values ESCO published, and states how each
tariff is set under the Electricity Market Rules (Article 36¹(2) for the
small-plants tariff, Article 14(3) for the sold tariff). The May-August
small-plants values are checked against the Enguri HPP tariff on every load.

Layout follows the dashboard's house style: page title, one-line intro, section
sub-headings, bordered cards, a caption under every chart and one data-notes
expander at the bottom.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
PROCESSED_DIR: Path = REPO_ROOT / "data" / "processed" / "esco"

REQUIRED_COLUMNS: list[str] = [
    "date",
    "year",
    "month_number",
    "month",
    "tariff_tetri_per_kwh",
    "tariff_gel_per_mwh",
]

MONTH_ABBREVIATIONS: list[str] = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

# In the published data, the small-plants tariff is a single fixed value in these
# months every year. The same window is used for both series so they compare
# like for like.
SUMMER_MONTHS: tuple[int, ...] = (5, 6, 7, 8)
SUMMER_LABEL: str = "May–Aug"
REST_OF_YEAR_LABEL: str = "Rest of year (Jan–Apr, Sep–Dec)"

RETRIEVAL_DATE: str = "2026-10-13"

# Enguri HPP tariff set by GNERC, tetri/kWh. Under Article 36¹(2) of the Electricity
# Market Rules, ESCO pays small plants this tariff for balancing electricity in May-August.
ENGURI_TARIFF_TETRI_PER_KWH: dict[int, float] = {2022: 1.857, 2023: 1.857, 2024: 2.412, 2025: 4.021}
SMALL_PLANTS_KEY: str = "purchased_small_plants"
TARIFF_TOLERANCE_TETRI: float = 0.0005

logger: logging.Logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TariffSeries:
    """Display definition of one regulated ESCO balancing tariff series.

    Attributes:
        key: Internal identifier.
        label: Short name used in headings, legends and cards.
        description: One-sentence definition of the tariff.
        path: Path to the processed tariff CSV.
        source_url: ESCO page the raw values were transcribed from.
    """

    key: str
    label: str
    description: str
    path: Path
    source_url: str


SERIES: tuple[TariffSeries, ...] = (
    TariffSeries(
        key="sold",
        label="Sold by ESCO",
        description="Weighted average tariff at which ESCO sells balancing electricity.",
        path=PROCESSED_DIR / "balancing_tariff_sold_monthly_clean.csv",
        source_url="https://esco.ge/ka/electricity/balancing-electricity-price",
    ),
    TariffSeries(
        key="purchased_small_plants",
        label="Paid to small plants",
        description=(
            "Tariff ESCO pays to purchase balancing electricity from "
            "small-capacity deregulated power plants."
        ),
        path=PROCESSED_DIR / "balancing_tariff_purchased_small_plants_monthly_clean.csv",
        source_url=(
            "https://esco.ge/ka/electricity/"
            "balancing-electricity-price-of-the-deregulated-power-plants"
        ),
    ),
)


@st.cache_data
def load_tariff(path_str: str) -> pd.DataFrame:
    """Load one processed tariff CSV and check its structure.

    Args:
        path_str: Path to the processed tariff CSV, as a string (hashable for
            Streamlit's cache).

    Returns:
        DataFrame sorted by date, with date parsed as datetime.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file cannot be parsed or is missing required columns.
    """
    path = Path(path_str)
    try:
        tariff_df = pd.read_csv(path, encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Processed tariff file not found: {path.name}") from exc
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise ValueError(f"Could not read processed tariff file {path.name}: {exc}") from exc

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in tariff_df.columns]
    if missing_columns:
        raise ValueError(f"{path.name} is missing required columns: {missing_columns}")

    tariff_df["date"] = pd.to_datetime(tariff_df["date"], format="%Y-%m-%d")
    return tariff_df.sort_values("date").reset_index(drop=True)


def load_all_series() -> dict[str, pd.DataFrame]:
    """Load every tariff series, stopping the page with a clear message on failure.

    Returns:
        Mapping of series key to its DataFrame.
    """
    try:
        return {series.key: load_tariff(str(series.path)) for series in SERIES}
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Balancing tariff page could not load data: %s", exc)
        st.error(f"Balancing tariff data could not be loaded: {exc}")
        st.stop()


def to_display_table(table: pd.DataFrame) -> pd.DataFrame:
    """Convert text columns to plain object dtype before st.dataframe.

    pandas 3's default string dtype crashes st.dataframe's Arrow serialisation
    (streamlit/streamlit#14609); the same workaround is used on the Electricity
    Balance page.

    Args:
        table: Table to display.

    Returns:
        Copy of the table that is safe to pass to st.dataframe.
    """
    display_table = table.copy()
    for column in display_table.select_dtypes(include=["string", "object"]).columns:
        display_table[column] = display_table[column].astype(object)
    return display_table


def format_month_list(dates: pd.Series) -> str:
    """Describe one or more months compactly, grouping consecutive months per year.

    Examples: "Jul 2024", "May–Aug 2022; May–Aug 2023".

    Args:
        dates: Dates of the months to describe.

    Returns:
        Human-readable description of the months.
    """
    months_by_year: dict[int, list[int]] = {}
    for date_value in sorted(pd.to_datetime(dates)):
        months_by_year.setdefault(date_value.year, []).append(date_value.month)

    parts: list[str] = []
    for year, months in months_by_year.items():
        is_consecutive_run = len(months) > 1 and months == list(range(months[0], months[-1] + 1))
        if is_consecutive_run:
            parts.append(f"{MONTH_ABBREVIATIONS[months[0] - 1]}–{MONTH_ABBREVIATIONS[months[-1] - 1]} {year}")
        else:
            parts.append(", ".join(f"{MONTH_ABBREVIATIONS[month - 1]} {year}" for month in months))
    return "; ".join(parts)


def render_card(column, label: str, value: str, footnote: str) -> None:
    """Render one bordered card: the value, with a short footnote in the grey line below.

    Args:
        column: Streamlit column to render into.
        label: Card label.
        value: Main value.
        footnote: Short text under the value (no arrow, no colour).
    """
    column.metric(label, value, delta=footnote, delta_color="off", delta_arrow="off", border=True)


def render_header() -> None:
    """Render the page title, intro and the regulated-tariff statement."""
    st.title("Balancing Tariffs")
    st.write("The two regulated tariffs ESCO uses to settle balancing electricity, and how each is set.")
    st.caption(
        "Regulated ESCO settlement tariffs, not market prices. Monthly values, "
        "2022–2025, in GEL/MWh (converted from the published tetri/kWh × 10)."
    )


def check_summer_small_plants(small_plants_df: pd.DataFrame) -> list[str]:
    """Compare the May-August small-plants values with the Enguri HPP tariff, year by year.

    Args:
        small_plants_df: DataFrame for the small-plants tariff.

    Returns:
        Plain-language mismatches; empty if every May-August value equals the
        Enguri tariff for its year.
    """
    mismatches: list[str] = []
    summer = small_plants_df[small_plants_df["month_number"].isin(SUMMER_MONTHS)]
    for year, values in summer.groupby("year")["tariff_tetri_per_kwh"]:
        expected = ENGURI_TARIFF_TETRI_PER_KWH.get(int(year))
        if expected is None:
            mismatches.append(f"{year}: no Enguri tariff on record")
        elif (values - expected).abs().max() > TARIFF_TOLERANCE_TETRI:
            mismatches.append(f"{year}: May–Aug values differ from the Enguri tariff ({expected} tetri/kWh)")
    return mismatches


def render_mechanism(data: dict[str, pd.DataFrame]) -> None:
    """Render how each tariff is set, with a data check of the May-August rule.

    Args:
        data: Mapping of series key to its DataFrame.
    """
    st.subheader("How the tariffs are set")
    st.markdown(
        f"""
- **{SERIES[1].label}** (Electricity Market Rules, Article 36¹(2)). From May to August, ESCO
  pays the Enguri HPP tariff set by GNERC. From September to April, it pays the highest price
  among standard contracts in that month, so the value changes month to month.
- **{SERIES[0].label}** (Article 14(3)). The monthly weighted average of what ESCO paid for all
  the balancing electricity it bought, so it moves every month.
"""
    )
    mismatches = check_summer_small_plants(data[SMALL_PLANTS_KEY])
    if mismatches:
        st.warning("May–August check: " + "; ".join(mismatches) + ".")
    else:
        years = sorted(ENGURI_TARIFF_TETRI_PER_KWH)
        st.caption(
            "Check on the published data: every May–August value of the small-plants tariff equals "
            f"the Enguri tariff for its year ({years[0]}–{years[-1]}: 1.857 tetri/kWh in 2022–2023, "
            "2.412 in 2024, 4.021 in 2025)."
        )


def render_overview(data: dict[str, pd.DataFrame]) -> None:
    """Render average, highest and lowest month cards for each tariff.

    Args:
        data: Mapping of series key to its DataFrame.
    """
    st.subheader("Overview, 2022–2025")

    for series in SERIES:
        tariff_df = data[series.key]
        values = tariff_df["tariff_gel_per_mwh"]
        highest_value = values.max()
        lowest_value = values.min()
        highest_months = tariff_df.loc[values == highest_value, "date"]
        lowest_months = tariff_df.loc[values == lowest_value, "date"]

        st.markdown(f"#### {series.label}")
        average_column, highest_column, lowest_column = st.columns(3)

        render_card(
            average_column,
            "Average",
            f"{values.mean():,.1f} GEL/MWh",
            f"Simple average of {len(values)} months",
        )
        render_card(
            highest_column,
            "Highest month",
            f"{highest_value:,.1f} GEL/MWh",
            format_month_list(highest_months),
        )
        render_card(
            lowest_column,
            "Lowest month",
            f"{lowest_value:,.1f} GEL/MWh",
            format_month_list(lowest_months),
        )

    st.caption("Averages are simple averages of monthly values, not volume-weighted.")


def render_monthly_charts(data: dict[str, pd.DataFrame]) -> None:
    """Render one monthly line chart per tariff, each on its own scale.

    Args:
        data: Mapping of series key to its DataFrame.
    """
    st.subheader("Monthly tariffs")

    for series in SERIES:
        figure = px.line(
            data[series.key],
            x="date",
            y="tariff_gel_per_mwh",
            markers=True,
            labels={"date": "Month", "tariff_gel_per_mwh": "GEL/MWh"},
            title=f"{series.label}: Monthly Tariff, GEL/MWh",
        )
        figure.update_traces(hovertemplate="%{x|%b %Y}<br>%{y:,.2f} GEL/MWh<extra></extra>")
        st.plotly_chart(figure, width="stretch")

    st.caption("Each tariff is shown on its own scale. Source: ESCO.")


def render_annual_averages(data: dict[str, pd.DataFrame]) -> None:
    """Render grouped bars of the simple annual average of each tariff.

    Args:
        data: Mapping of series key to its DataFrame.
    """
    st.subheader("Annual average tariffs")

    annual_frames = []
    for series in SERIES:
        annual = data[series.key].groupby("year", as_index=False)["tariff_gel_per_mwh"].mean()
        annual["Tariff"] = series.label
        annual_frames.append(annual)
    annual_df = pd.concat(annual_frames, ignore_index=True)
    annual_df["year"] = annual_df["year"].astype(str)

    figure = px.bar(
        annual_df,
        x="year",
        y="tariff_gel_per_mwh",
        color="Tariff",
        barmode="group",
        text_auto=".1f",
        labels={"year": "Year", "tariff_gel_per_mwh": "GEL/MWh (simple average)"},
        title="Annual Average Tariff, GEL/MWh",
    )
    st.plotly_chart(figure, width="stretch")
    st.caption("Simple average of the 12 monthly values in each year, not volume-weighted.")


def render_seasonal_heatmaps(data: dict[str, pd.DataFrame]) -> None:
    """Render one month-by-year heatmap per tariff, side by side.

    Args:
        data: Mapping of series key to its DataFrame.
    """
    st.subheader("Seasonal pattern: month by year")

    columns = st.columns(len(SERIES))
    for column, series in zip(columns, SERIES):
        pivot = data[series.key].pivot(index="year", columns="month_number", values="tariff_gel_per_mwh")
        pivot = pivot.reindex(columns=range(1, 13))

        figure = px.imshow(
            pivot.to_numpy(),
            x=MONTH_ABBREVIATIONS,
            y=[str(year) for year in pivot.index],
            text_auto=".0f",
            aspect="auto",
            color_continuous_scale="Blues",
            labels={"x": "Month", "y": "Year", "color": "GEL/MWh"},
            title=series.label,
        )
        with column:
            st.plotly_chart(figure, width="stretch")

    st.caption("Values in GEL/MWh. Darker cells mean a higher tariff within that series.")


def build_seasonal_split(tariff_df: pd.DataFrame) -> pd.DataFrame:
    """Average each year's tariff separately for May-August and the rest of the year.

    Args:
        tariff_df: DataFrame for one series.

    Returns:
        DataFrame with columns year (str), Period and tariff_gel_per_mwh.
    """
    split_df = tariff_df.copy()
    split_df["Period"] = split_df["month_number"].isin(SUMMER_MONTHS).map(
        {True: SUMMER_LABEL, False: REST_OF_YEAR_LABEL}
    )
    seasonal_df = split_df.groupby(["year", "Period"], as_index=False)["tariff_gel_per_mwh"].mean()
    seasonal_df["year"] = seasonal_df["year"].astype(str)
    return seasonal_df


def render_seasonal_split(data: dict[str, pd.DataFrame]) -> None:
    """Render May-August versus rest-of-year averages for each tariff.

    Args:
        data: Mapping of series key to its DataFrame.
    """
    st.subheader("May–August versus the rest of the year")

    columns = st.columns(len(SERIES))
    for column, series in zip(columns, SERIES):
        figure = px.bar(
            build_seasonal_split(data[series.key]),
            x="year",
            y="tariff_gel_per_mwh",
            color="Period",
            barmode="group",
            text_auto=".1f",
            category_orders={"Period": [REST_OF_YEAR_LABEL, SUMMER_LABEL]},
            labels={"year": "Year", "tariff_gel_per_mwh": "GEL/MWh (simple average)"},
            title=series.label,
        )
        figure.update_layout(legend=dict(orientation="h", y=-0.25, x=0.5, xanchor="center", title=None))
        with column:
            st.plotly_chart(figure, width="stretch")

    st.caption(
        "Simple averages of monthly values within each period. May–August is used for "
        "both tariffs because that is when the small-plants tariff is fixed at the "
        "Enguri HPP tariff."
    )


def build_stability_table(tariff_df: pd.DataFrame) -> pd.DataFrame:
    """Summarise each year's level and variability for one tariff.

    Args:
        tariff_df: DataFrame for one series.

    Returns:
        Table with one row per year: average, lowest, highest, range and the
        coefficient of variation (standard deviation divided by the average).
    """
    grouped = tariff_df.groupby("year")["tariff_gel_per_mwh"]
    table = pd.DataFrame(
        {
            "Average": grouped.mean(),
            "Lowest": grouped.min(),
            "Highest": grouped.max(),
        }
    )
    table["Range"] = table["Highest"] - table["Lowest"]
    table["Variability (CV %)"] = grouped.std() / grouped.mean() * 100
    table = table.round(1).reset_index().rename(columns={"year": "Year"})
    table["Year"] = table["Year"].astype(str)
    return to_display_table(table)


def render_stability_tables(data: dict[str, pd.DataFrame]) -> None:
    """Render the per-year stability table for each tariff, side by side.

    Args:
        data: Mapping of series key to its DataFrame.
    """
    st.subheader("Stability by year")

    columns = st.columns(len(SERIES))
    for column, series in zip(columns, SERIES):
        with column:
            st.markdown(f"#### {series.label} (GEL/MWh)")
            st.dataframe(build_stability_table(data[series.key]), width="stretch", hide_index=True)

    st.caption(
        "Variability (CV %) is the standard deviation of the 12 monthly values divided by "
        "their average. Higher means the tariff moved more within that year. For the "
        "small-plants tariff it is driven mainly by the fixed May–August (Enguri) value."
    )


def render_data_notes() -> None:
    """Render definitions, method notes and sources."""
    with st.expander("Data notes"):
        st.markdown(
            f"""
**What these are.** Two regulated ESCO settlement tariffs for balancing
electricity. They are not market prices.

- **{SERIES[0].label}:** {SERIES[0].description}
- **{SERIES[1].label}:** {SERIES[1].description}

**How to read them.** The two series are opposite sides of a transaction:
what ESCO sells at, and what ESCO pays small plants. They are not two versions
of the same measure.

**Method notes**

- Values are converted from the published tetri/kWh to GEL/MWh (× 10).
- All averages are simple averages of monthly values, not volume-weighted.
- From May to August the small-plants tariff equals the Enguri HPP tariff
  (Article 36¹(2)); this is checked against the published data on every load.
- July 2024 (sold tariff) was published as "15,6159665" with a comma decimal
  separator. It is corrected to 15.6159665 during processing, and the
  correction is logged.

**Sources** (transcribed manually from the ESCO website, retrieved {RETRIEVAL_DATE})

- {SERIES[0].label}: {SERIES[0].source_url}
- {SERIES[1].label}: {SERIES[1].source_url}
"""
        )


def main() -> None:
    """Render the balancing electricity tariffs page."""
    render_header()
    data = load_all_series()

    render_mechanism(data)
    render_overview(data)
    render_monthly_charts(data)
    render_annual_averages(data)
    render_seasonal_heatmaps(data)
    render_seasonal_split(data)
    render_stability_tables(data)
    render_data_notes()


main()