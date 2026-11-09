"""Balancing market: supply by seller category (volumes only).

Adds one section to the Electricity Balance page. It reads the ESCO seller-side
report (data/processed/esco/supply_by_category_monthly_clean.csv) and shows how
much electricity each seller category contributed to ESCO's balancing pool.

Scope is deliberately limited to physical volumes in GWh. The section contains no
tariffs, prices, costs or buyer-side data, and makes no causal statements.

The module can also be run directly as a self-check against the agreed
acceptance numbers:

    python dashboard/supply_by_category.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

BASE_DIR: Path = Path(__file__).resolve().parents[1]
SUPPLY_FILE: Path = (
    BASE_DIR / "data" / "processed" / "esco" / "supply_by_category_monthly_clean.csv"
)

REQUIRED_COLUMNS: list[str] = [
    "period",
    "year",
    "month",
    "category",
    "supply_gwh",
    "non_balancing_gwh",
    "balancing_gwh",
]
VALUE_COLUMNS: list[str] = ["supply_gwh", "non_balancing_gwh", "balancing_gwh"]

EXPECTED_ROWS: int = 432
EXPECTED_MONTHS: int = 48

# Source category -> display series. Six series are shown; three deregulated hydro
# categories are combined, and so are the fixed-rate hydro and support-scheme ones.
CATEGORY_TO_SERIES: dict[str, str] = {
    "imports": "Imports",
    "hydro_guaranteed_purchase": "Guaranteed-purchase hydro",
    "thermal_gardabani_2_guaranteed": "Gardabani TPP 2",
    "thermal_other": "Other thermal",
    "hydro_deregulated_under_13mw": "Deregulated hydro",
    "hydro_deregulated_13_40mw": "Deregulated hydro",
    "hydro_deregulated_upper_limit": "Deregulated hydro",
    "hydro_fixed_tariff": "Enguri/Vardnili + CfD",
    "support_scheme": "Enguri/Vardnili + CfD",
}
SERIES_ORDER: list[str] = [
    "Guaranteed-purchase hydro",
    "Gardabani TPP 2",
    "Other thermal",
    "Imports",
    "Deregulated hydro",
    "Enguri/Vardnili + CfD",
]
# Fixed colour per series, so a series keeps its colour whichever year is selected.
SERIES_COLOURS: dict[str, str] = {
    series: px.colors.qualitative.Plotly[index] for index, series in enumerate(SERIES_ORDER)
}

# Agreed acceptance numbers (year -> supply GWh, balancing GWh, pool % of supply).
ACCEPTANCE_TOTALS: dict[int, tuple[float, float, float]] = {
    2022: (15521.1, 3196.8, 20.6),
    2023: (14917.1, 2491.9, 16.7),
    2024: (15209.7, 4139.9, 27.2),
    2025: (15125.3, 4453.4, 29.4),
}
# Agreed acceptance numbers: series -> % of pool for 2022, 2023, 2024, 2025.
ACCEPTANCE_SHARES: dict[str, tuple[float, float, float, float]] = {
    "Guaranteed-purchase hydro": (49.1, 62.3, 46.1, 43.3),
    "Gardabani TPP 2": (27.9, 32.4, 26.1, 19.1),
    "Other thermal": (1.6, 0.8, 11.0, 17.3),
    "Imports": (19.3, 0.5, 13.7, 18.7),
    "Deregulated hydro": (1.9, 3.9, 2.1, 0.1),
    "Enguri/Vardnili + CfD": (0.3, 0.0, 1.1, 1.5),
}

logger: logging.Logger = logging.getLogger(__name__)


class SupplyDataError(ValueError):
    """Raised when the supply-by-category file is missing or fails validation."""


def to_display_table(table: pd.DataFrame) -> pd.DataFrame:
    """Convert text columns to plain object dtype before st.dataframe.

    pandas 3's default string dtype crashes st.dataframe's Arrow serialisation
    (streamlit/streamlit#14609); this is the same workaround used in load_data().

    Args:
        table: Table to display.

    Returns:
        Copy of the table that is safe to pass to st.dataframe.
    """
    display_table = table.copy()
    for column in display_table.select_dtypes(include=["string", "object"]).columns:
        display_table[column] = display_table[column].astype(object)
    return display_table


def read_supply_file(path: Path) -> pd.DataFrame:
    """Read and validate the supply-by-category file.

    Args:
        path: Path to supply_by_category_monthly_clean.csv.

    Returns:
        DataFrame with the original columns plus date (first of month) and series.

    Raises:
        SupplyDataError: With a plain-language message if the file is missing,
            unreadable or fails any structural check.
    """
    try:
        supply_df = pd.read_csv(path, encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise SupplyDataError(f"data file not found ({path.name})") from exc
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise SupplyDataError(f"data file {path.name} could not be read") from exc

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in supply_df.columns]
    if missing_columns:
        raise SupplyDataError(f"data file is missing columns: {', '.join(missing_columns)}")

    if len(supply_df) != EXPECTED_ROWS:
        raise SupplyDataError(f"expected {EXPECTED_ROWS} rows, found {len(supply_df)}")

    if supply_df[REQUIRED_COLUMNS].isna().any().any():
        raise SupplyDataError("data file contains empty values")

    unknown_categories = sorted(set(supply_df["category"]) - set(CATEGORY_TO_SERIES))
    found_categories = supply_df["category"].nunique()
    if unknown_categories or found_categories != len(CATEGORY_TO_SERIES):
        raise SupplyDataError(
            f"expected {len(CATEGORY_TO_SERIES)} known seller categories, found "
            f"{found_categories} (unknown: {', '.join(unknown_categories) or 'none'})"
        )

    try:
        for column in VALUE_COLUMNS:
            supply_df[column] = pd.to_numeric(supply_df[column], errors="raise")
        supply_df["date"] = pd.to_datetime(
            {"year": supply_df["year"], "month": supply_df["month"], "day": 1}
        )
    except (ValueError, TypeError) as exc:
        raise SupplyDataError("data file contains non-numeric values or invalid dates") from exc

    months = supply_df["date"].nunique()
    if months != EXPECTED_MONTHS:
        raise SupplyDataError(f"expected {EXPECTED_MONTHS} months, found {months}")

    if supply_df.duplicated(["date", "category"]).any():
        raise SupplyDataError("data file contains duplicate month and category rows")

    supply_df["series"] = supply_df["category"].map(CATEGORY_TO_SERIES)
    return supply_df.sort_values(["date", "category"]).reset_index(drop=True)


@st.cache_data
def load_supply_data(path_str: str) -> pd.DataFrame:
    """Cached wrapper around read_supply_file.

    Args:
        path_str: Path to the supply file as a string (hashable for the cache).

    Returns:
        Validated supply DataFrame.

    Raises:
        SupplyDataError: If the file is missing or invalid.
    """
    supply_df = read_supply_file(Path(path_str))
    for column in supply_df.select_dtypes(include=["string", "object"]).columns:
        supply_df[column] = supply_df[column].astype(object)
    return supply_df


def build_monthly_pool(supply_df: pd.DataFrame) -> pd.DataFrame:
    """Balancing-pool volume per month and display series.

    Args:
        supply_df: Validated supply DataFrame.

    Returns:
        DataFrame with columns date, series, balancing_gwh.
    """
    return supply_df.groupby(["date", "series"], as_index=False)["balancing_gwh"].sum()


def build_monthly_pool_share(supply_df: pd.DataFrame) -> pd.DataFrame:
    """Balancing pool as a percentage of total supply, per month.

    Args:
        supply_df: Validated supply DataFrame.

    Returns:
        DataFrame with columns date and pool_pct_of_supply.
    """
    monthly = supply_df.groupby("date", as_index=False)[["supply_gwh", "balancing_gwh"]].sum()
    safe_supply = monthly["supply_gwh"].where(monthly["supply_gwh"] != 0)
    monthly["pool_pct_of_supply"] = (monthly["balancing_gwh"] / safe_supply * 100).fillna(0.0)
    return monthly[["date", "pool_pct_of_supply"]]


def build_annual_totals(supply_df: pd.DataFrame) -> pd.DataFrame:
    """Total supply, pool size and pool share of supply per year.

    Args:
        supply_df: Validated supply DataFrame.

    Returns:
        DataFrame indexed by year with supply_gwh, balancing_gwh, pool_pct_of_supply.
    """
    totals = supply_df.groupby("year")[["supply_gwh", "balancing_gwh"]].sum()
    safe_supply = totals["supply_gwh"].where(totals["supply_gwh"] != 0)
    totals["pool_pct_of_supply"] = (totals["balancing_gwh"] / safe_supply * 100).fillna(0.0)
    return totals


def build_annual_shares(supply_df: pd.DataFrame) -> pd.DataFrame:
    """Each series' share of the balancing pool, per year.

    Args:
        supply_df: Validated supply DataFrame.

    Returns:
        DataFrame indexed by year, one column per series in SERIES_ORDER, in %.
    """
    by_series = supply_df.groupby(["year", "series"])["balancing_gwh"].sum().unstack("series")
    by_series = by_series.reindex(columns=SERIES_ORDER).fillna(0.0)
    pool = by_series.sum(axis=1).where(lambda total: total != 0)
    return by_series.div(pool, axis=0).mul(100).fillna(0.0)


def build_annual_table(supply_df: pd.DataFrame) -> pd.DataFrame:
    """Assemble the display table: pool size, pool share of supply and series shares.

    Args:
        supply_df: Supply DataFrame (already filtered to the selected years).

    Returns:
        Display-ready DataFrame with one row per year.
    """
    totals = build_annual_totals(supply_df)
    shares = build_annual_shares(supply_df)

    table = pd.DataFrame(
        {
            "Year": totals.index.astype(str),
            "Total supply (GWh)": totals["supply_gwh"].round(1).to_numpy(),
            "Balancing pool (GWh)": totals["balancing_gwh"].round(1).to_numpy(),
            "Pool, % of supply": totals["pool_pct_of_supply"].round(1).to_numpy(),
        }
    )
    for series in SERIES_ORDER:
        table[f"{series}, % of pool"] = shares[series].round(1).to_numpy()
    return to_display_table(table)


def render_data_notes() -> None:
    """Render the data-notes expander."""
    with st.expander("Data notes"):
        st.markdown(
            """
- **July 2024.** The balancing pool in this report is 0.694 GWh short of ESCO's
  official figure for that month, because the dispatcher line is not part of the
  seller total.
- **"Other thermal"** is the thermal total minus Gardabani TPP 2.
- **Series grouping.** "Deregulated hydro" combines three deregulated hydro
  categories (under 13 MW, 13–40 MW and upper limit). "Enguri/Vardnili + CfD"
  combines the Enguri/Vardnili category and the support scheme.
- **Unit.** The source sheet does not state the unit. GWh is assumed, and has
  not yet been confirmed against the source sheet.
"""
        )

def render_supply_by_category_section() -> None:
    """Render the 'Balancing market: supply by seller category' section.

    Shows physical volumes only. On any data problem it shows a plain error
    message inside the section and returns, so the rest of the page still renders.
    """
    st.subheader("Supply by seller category")

    try:
        supply_df = load_supply_data(str(SUPPLY_FILE))
    except SupplyDataError as exc:
        logger.error("Supply by category could not be loaded: %s", exc)
        st.error(f"Supply by category could not be loaded: {exc}.")
        return
    except Exception:  # UI boundary: a failure here must never take the page down
        logger.exception("Unexpected error loading supply by category")
        st.error("Supply by category could not be loaded because of an unexpected error.")
        return

    st.caption(
        "ESCO seller-side report. Balancing = electricity sold through ESCO's balancing pool; "
        "the rest is direct contract (from mid-2024 also exchange). Unit assumed GWh."
    )

    years = sorted(supply_df["year"].unique().tolist())
    selected = st.radio(
        "Year (this section)",
        ["All", *years],
        horizontal=True,
        key="supply_by_category_year",
    )
    view_df = supply_df if selected == "All" else supply_df[supply_df["year"] == selected]

    pool_df = build_monthly_pool(view_df)
    figure_pool = px.bar(
        pool_df,
        x="date",
        y="balancing_gwh",
        color="series",
        category_orders={"series": SERIES_ORDER},
        color_discrete_map=SERIES_COLOURS,
        labels={"date": "Month", "balancing_gwh": "GWh", "series": "Seller category"},
        title="Balancing Pool by Seller Category, GWh",
    )
    # px gives every colour its own offset group, which plotly.js 3.x (bundled with
    # Streamlit) draws side by side even in stack mode. One shared offset group makes
    # the six series stack into a single bar per month.
    figure_pool.update_traces(
        offsetgroup="pool",
        hovertemplate="%{y:,.1f} GWh",
    )
    figure_pool.update_layout(barmode="stack", bargap=0.15, hovermode="x unified")
    figure_pool.update_yaxes(title_text="GWh")
    figure_pool.update_xaxes(title_text="Month", hoverformat="%b %Y")
    st.plotly_chart(figure_pool, width="stretch")

    share_df = build_monthly_pool_share(view_df)
    figure_share = px.line(
        share_df,
        x="date",
        y="pool_pct_of_supply",
        markers=True,
        labels={"date": "Month", "pool_pct_of_supply": "Balancing pool (% of total supply)"},
        title="Balancing Pool as a Share of Total Supply",
    )
    figure_share.update_yaxes(
        title_text="Balancing pool (% of total supply)", ticksuffix="%", rangemode="tozero"
    )
    figure_share.update_xaxes(title_text="Month")
    st.plotly_chart(figure_share, width="stretch")

    st.markdown("#### Pool composition by year")
    st.dataframe(build_annual_table(view_df), width="stretch", hide_index=True)
    st.caption(
        "Percentages by seller category are shares of the balancing pool in that year. "
        "Pool, % of supply is the balancing pool divided by total supply."
    )

    render_data_notes()

def run_acceptance_check(path: Path = SUPPLY_FILE) -> bool:
    """Compare the file against the agreed acceptance numbers and log the result.

    Args:
        path: Path to the supply file.

    Returns:
        True if every number matches, False otherwise.
    """
    try:
        supply_df = read_supply_file(path)
    except SupplyDataError as exc:
        logger.error("Validation failed: %s", exc)
        return False

    logger.info("Validation passed: %d rows, %d months", len(supply_df), supply_df["date"].nunique())
    totals = build_annual_totals(supply_df)
    shares = build_annual_shares(supply_df)
    mismatches = 0

    for year, (supply_gwh, balancing_gwh, pool_pct) in ACCEPTANCE_TOTALS.items():
        actual = (
            round(float(totals.loc[year, "supply_gwh"]), 1),
            round(float(totals.loc[year, "balancing_gwh"]), 1),
            round(float(totals.loc[year, "pool_pct_of_supply"]), 1),
        )
        expected = (supply_gwh, balancing_gwh, pool_pct)
        ok = all(abs(a - e) < 1e-6 for a, e in zip(actual, expected))
        mismatches += 0 if ok else 1
        logger.log(
            logging.INFO if ok else logging.ERROR,
            "%d supply/pool/pool%%: expected %s | actual %s | %s",
            year, expected, actual, "OK" if ok else "MISMATCH",
        )

    for series, expected_shares in ACCEPTANCE_SHARES.items():
        actual_shares = tuple(round(float(shares.loc[year, series]), 1) for year in ACCEPTANCE_TOTALS)
        ok = all(abs(a - e) < 1e-6 for a, e in zip(actual_shares, expected_shares))
        mismatches += 0 if ok else 1
        logger.log(
            logging.INFO if ok else logging.ERROR,
            "%s %% of pool 2022-2025: expected %s | actual %s | %s",
            series, expected_shares, actual_shares, "OK" if ok else "MISMATCH",
        )

    logger.info("Acceptance check: %s", "ALL MATCH" if mismatches == 0 else f"{mismatches} MISMATCHES")
    return mismatches == 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    sys.exit(0 if run_acceptance_check() else 1)