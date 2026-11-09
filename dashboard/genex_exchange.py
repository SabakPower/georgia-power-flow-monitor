"""GENEX day-ahead exchange: volume, traded price and ESCO comparison for the GENEX Day-Ahead page.

Reads the processed GENEX day-ahead files (data/processed/genex/) and shows how much
energy cleared on the exchange, month by month and year by year, next to ESCO's
annual supply. It also shows the traded price on GENEX (monthly, volume-weighted) and a
descriptive comparison with ESCO's balancing tariff (sold). ESCO's figure is a regulated
settlement tariff, not a market price. No statements about who trades or why.

The CSVs have passed through Excel, so dates may be written as M/D/YYYY. The
loaders accept both M/D/YYYY and YYYY-MM-DD, and build monthly dates from the
year and month columns. Months are keyed internally as YYYY-MM (month_label) and
shown to readers as "Jun 2025" (month_display).

The module can also be run directly as a self-check against the agreed
acceptance numbers:

    python dashboard/genex_exchange.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from supply_by_category import SUPPLY_FILE, load_supply_data

BASE_DIR: Path = Path(__file__).resolve().parents[1]
GENEX_DIR: Path = BASE_DIR / "data" / "processed" / "genex"
DAILY_FILE: Path = GENEX_DIR / "genex_dam_daily_clean.csv"
MONTHLY_FILE: Path = GENEX_DIR / "genex_dam_monthly_clean.csv"
COMPARISON_FILE: Path = GENEX_DIR / "genex_vs_esco_monthly.csv"

EXPECTED_DAILY_ROWS: int = 171
EXPECTED_MONTHLY_ROWS: int = 27
EXPECTED_COMPARISON_ROWS: int = 13

DAILY_COLUMNS: list[str] = [
    "date",
    "hours_traded",
    "volume_mwh",
    "price_gel_per_mwh",
    "price_gel_min",
    "price_gel_max",
    "data_quality_flag",
]
MONTHLY_COLUMNS: list[str] = [
    "period",
    "year",
    "month",
    "days_traded",
    "hours_traded",
    "volume_mwh",
    "volume_gwh",
    "price_gel_per_mwh",
    "esco_supply_gwh",
    "exchange_share_of_supply_pct",
    "data_quality_flag",
]
DAILY_NUMERIC: list[str] = ["hours_traded", "volume_mwh", "price_gel_per_mwh", "price_gel_min", "price_gel_max"]
MONTHLY_REQUIRED_NUMERIC: list[str] = ["year", "month", "days_traded", "hours_traded", "volume_mwh", "volume_gwh"]
MONTHLY_OPTIONAL_NUMERIC: list[str] = ["price_gel_per_mwh", "esco_supply_gwh", "exchange_share_of_supply_pct"]
COMPARISON_COLUMNS: list[str] = [
    "period",
    "year",
    "month",
    "days_traded",
    "volume_mwh",
    "genex_price_gel_mwh",
    "esco_series2_gel_mwh",
    "gap_gel_mwh",
    "gap_pct",
    "saving_gel",
    "representative_month",
]
COMPARISON_NUMERIC: list[str] = [
    "year",
    "month",
    "days_traded",
    "volume_mwh",
    "genex_price_gel_mwh",
    "esco_series2_gel_mwh",
    "gap_gel_mwh",
    "gap_pct",
    "saving_gel",
]
# A month counts as representative with 10 or more traded days.
REPRESENTATIVE_YES: str = "yes"
REPRESENTATIVE_VALUES: set[str] = {"yes", "no_fewer_than_10_traded_days"}

# Dates may be M/D/YYYY (Excel round trip) or YYYY-MM-DD (script output).
DATE_FORMATS: tuple[str, ...] = ("%m/%d/%Y", "%Y-%m-%d")

# Tolerance when comparing a monthly volume with the sum of its daily volumes (MWh).
DAILY_MONTHLY_TOLERANCE_MWH: float = 1.0
# Tolerances for the comparison file: prices and gaps are rounded to 0.01 GEL/MWh,
# gap percentages to 0.1 percentage points.
PRICE_TOLERANCE_GEL: float = 0.011
GAP_PCT_TOLERANCE: float = 0.06

# Agreed acceptance numbers.
ACCEPTANCE_VOLUME_MWH: dict[int, float] = {2024: 17493.9, 2025: 129753.8, 2026: 41195.8}
ACCEPTANCE_TRADED_DAYS: dict[int, int] = {2024: 20, 2025: 116, 2026: 35}
ACCEPTANCE_TOTAL_GWH: float = 188.44
ACCEPTANCE_MONTHS: tuple[int, int, int] = (27, 13, 14)  # total, with volume, without
ACCEPTANCE_LARGEST_GWH: list[tuple[str, float]] = [("2025-06", 38.459), ("2025-05", 37.607), ("2025-07", 31.685)]
ACCEPTANCE_SHARE_PCT: dict[int, float] = {2024: 0.12, 2025: 0.86}
ACCEPTANCE_PRICE_GEL_PER_MWH: dict[str, float] = {
    "2024-07": 126.44,
    "2025-04": 150.94,
    "2025-05": 125.13,
    "2025-06": 126.05,
    "2025-07": 132.43,
    "2025-08": 144.13,
    "2026-05": 113.19,
    "2026-06": 109.93,
}
ACCEPTANCE_WEIGHTED_PRICE_2025: float = 131.40

# Price-chart markers grow with the number of traded days in the month.
MARKER_SIZE_MIN: float = 7.0
MARKER_SIZE_MAX: float = 22.0

# Comparison chart styling: weak months (fewer than 10 traded days) are faded.
GENEX_COLOUR: str = px.colors.qualitative.Plotly[0]
ESCO_COLOUR: str = px.colors.qualitative.Plotly[1]
CONNECTOR_COLOUR: str = "rgba(150, 150, 150, 0.8)"
FADED_OPACITY: float = 0.35

ACCEPTANCE_GAP_GEL_PER_MWH: dict[str, float] = {"2024-07": -29.72, "2025-04": -16.38, "2026-06": -31.06}
ACCEPTANCE_IMPLIED_GEL_BY_YEAR: dict[int, int] = {2024: 439874, 2025: 2264722, 2026: 1066546}
ACCEPTANCE_REPRESENTATIVE: tuple[int, float, float] = (7, -20.3, -13.8)  # months, mean gap, mean gap %

logger: logging.Logger = logging.getLogger(__name__)


class GenexDataError(ValueError):
    """Raised when a GENEX file is missing or fails validation."""


def to_object_dtype(table: pd.DataFrame) -> pd.DataFrame:
    """Convert text columns to plain object dtype.

    pandas 3's default string dtype crashes st.dataframe's Arrow serialisation
    (streamlit/streamlit#14609); this is the same workaround used in load_data().

    Args:
        table: Table to convert.

    Returns:
        Copy of the table with text columns as object dtype.
    """
    converted = table.copy()
    for column in converted.select_dtypes(include=["string", "object"]).columns:
        converted[column] = converted[column].astype(object)
    return converted


def read_csv_checked(path: Path, required_columns: list[str], label: str) -> pd.DataFrame:
    """Read a CSV and check that all required columns exist.

    Args:
        path: Path to the CSV.
        required_columns: Columns that must be present.
        label: Plain name of the file used in error messages.

    Returns:
        The raw DataFrame.

    Raises:
        GenexDataError: If the file is missing, unreadable or lacks columns.
    """
    try:
        table = pd.read_csv(path, encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise GenexDataError(f"{label} file not found ({path.name})") from exc
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise GenexDataError(f"{label} file {path.name} could not be read") from exc

    missing = [column for column in required_columns if column not in table.columns]
    if missing:
        raise GenexDataError(f"{label} file is missing columns: {', '.join(missing)}")
    return table


def parse_dates(values: pd.Series, label: str) -> pd.Series:
    """Parse dates written as M/D/YYYY or YYYY-MM-DD.

    Args:
        values: Date text.
        label: Plain name of the file used in error messages.

    Returns:
        Series of timestamps.

    Raises:
        GenexDataError: If the dates match neither format.
    """
    text = values.astype(str).str.strip()
    for date_format in DATE_FORMATS:
        parsed = pd.to_datetime(text, format=date_format, errors="coerce")
        if parsed.notna().all():
            return parsed
    raise GenexDataError(f"{label} file has dates in an unrecognised format")


def to_numeric_checked(table: pd.DataFrame, columns: list[str], label: str) -> pd.DataFrame:
    """Convert columns to numbers, failing loudly on any non-numeric value.

    Args:
        table: Table to convert.
        columns: Columns to convert.
        label: Plain name of the file used in error messages.

    Returns:
        Copy of the table with numeric columns.

    Raises:
        GenexDataError: If a value cannot be converted.
    """
    converted = table.copy()
    try:
        for column in columns:
            converted[column] = pd.to_numeric(converted[column], errors="raise")
    except (ValueError, TypeError) as exc:
        raise GenexDataError(f"{label} file contains non-numeric values") from exc
    return converted


def read_daily(path: Path) -> pd.DataFrame:
    """Read and validate the daily GENEX file (one row per traded day).

    Args:
        path: Path to genex_dam_daily_clean.csv.

    Returns:
        DataFrame sorted by date with a parsed date column.

    Raises:
        GenexDataError: If the file is missing or fails any check.
    """
    label = "GENEX daily"
    daily_df = read_csv_checked(path, DAILY_COLUMNS, label)

    if len(daily_df) != EXPECTED_DAILY_ROWS:
        raise GenexDataError(f"{label} file: expected {EXPECTED_DAILY_ROWS} rows, found {len(daily_df)}")
    if daily_df[DAILY_COLUMNS].isna().any().any():
        raise GenexDataError(f"{label} file contains empty values")

    daily_df = to_numeric_checked(daily_df, DAILY_NUMERIC, label)
    daily_df["date"] = parse_dates(daily_df["date"], label)

    if daily_df["date"].duplicated().any():
        raise GenexDataError(f"{label} file contains duplicate dates")
    if (daily_df["volume_mwh"] <= 0).any():
        raise GenexDataError(f"{label} file contains traded days with no volume")
    if not daily_df["hours_traded"].between(1, 24).all():
        raise GenexDataError(f"{label} file has hours traded outside 1-24")

    return daily_df.sort_values("date").reset_index(drop=True)


def read_monthly(path: Path) -> pd.DataFrame:
    """Read and validate the monthly GENEX file (27 consecutive months).

    Args:
        path: Path to genex_dam_monthly_clean.csv.

    Returns:
        DataFrame sorted by month with month_start (first of month), month_label
        (YYYY-MM, used as a key) and month_display ("Jun 2025", shown to readers).

    Raises:
        GenexDataError: If the file is missing or fails any check.
    """
    label = "GENEX monthly"
    monthly_df = read_csv_checked(path, MONTHLY_COLUMNS, label)

    if len(monthly_df) != EXPECTED_MONTHLY_ROWS:
        raise GenexDataError(f"{label} file: expected {EXPECTED_MONTHLY_ROWS} rows, found {len(monthly_df)}")
    if monthly_df[MONTHLY_REQUIRED_NUMERIC].isna().any().any():
        raise GenexDataError(f"{label} file contains empty values")

    monthly_df = to_numeric_checked(monthly_df, MONTHLY_REQUIRED_NUMERIC + MONTHLY_OPTIONAL_NUMERIC, label)
    try:
        monthly_df["month_start"] = pd.to_datetime(
            {"year": monthly_df["year"], "month": monthly_df["month"], "day": 1}
        )
    except (ValueError, TypeError) as exc:
        raise GenexDataError(f"{label} file has invalid year or month values") from exc

    monthly_df = monthly_df.sort_values("month_start").reset_index(drop=True)
    expected_months = pd.date_range(monthly_df["month_start"].iloc[0], periods=EXPECTED_MONTHLY_ROWS, freq="MS")
    if not (monthly_df["month_start"] == expected_months).all():
        raise GenexDataError(f"{label} file is not a run of {EXPECTED_MONTHLY_ROWS} consecutive months")

    traded = monthly_df["volume_mwh"] > 0
    if ((monthly_df["days_traded"] > 0) != traded).any():
        raise GenexDataError(f"{label} file: traded days and volume disagree")
    if monthly_df.loc[traded, "price_gel_per_mwh"].isna().any():
        raise GenexDataError(f"{label} file: a month with volume has no price")

    monthly_df["month_label"] = monthly_df["month_start"].dt.strftime("%Y-%m")
    monthly_df["month_display"] = monthly_df["month_start"].dt.strftime("%b %Y")
    return monthly_df


def check_daily_monthly_consistency(daily_df: pd.DataFrame, monthly_df: pd.DataFrame) -> None:
    """Check that monthly volumes and traded days agree with the daily file.

    Args:
        daily_df: Validated daily table.
        monthly_df: Validated monthly table.

    Raises:
        GenexDataError: If any month disagrees beyond rounding.
    """
    by_month = daily_df.groupby(daily_df["date"].dt.to_period("M").dt.to_timestamp()).agg(
        volume_mwh=("volume_mwh", "sum"), days=("date", "size")
    )
    reference = by_month.reindex(monthly_df["month_start"]).fillna(0.0)
    volume_gap = float(abs(reference["volume_mwh"].to_numpy() - monthly_df["volume_mwh"].to_numpy()).max())
    if volume_gap > DAILY_MONTHLY_TOLERANCE_MWH:
        raise GenexDataError("GENEX monthly volumes do not match the daily file")
    if (reference["days"].to_numpy() != monthly_df["days_traded"].to_numpy()).any():
        raise GenexDataError("GENEX monthly traded days do not match the daily file")


@st.cache_data
def load_genex_volume_data(daily_path_str: str, monthly_path_str: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load and validate the daily and monthly GENEX files.

    Args:
        daily_path_str: Path to the daily file as a string (hashable for the cache).
        monthly_path_str: Path to the monthly file as a string.

    Returns:
        Tuple of (daily table, monthly table).

    Raises:
        GenexDataError: If a file is missing or fails validation.
    """
    daily_df = read_daily(Path(daily_path_str))
    monthly_df = read_monthly(Path(monthly_path_str))
    check_daily_monthly_consistency(daily_df, monthly_df)
    return to_object_dtype(daily_df), to_object_dtype(monthly_df)


def load_annual_supply_gwh() -> dict[int, float]:
    """Yearly ESCO supply in GWh, for years with all 12 months of supply data.

    Returns:
        Mapping of year to supply GWh. Empty if the supply file cannot be read.
    """
    try:
        supply_df = load_supply_data(str(SUPPLY_FILE))
    except ValueError as exc:
        logger.warning("ESCO supply data unavailable, shares shown as n/a: %s", exc)
        return {}
    months_per_year = supply_df.groupby("year")["date"].nunique()
    totals = supply_df.groupby("year")["supply_gwh"].sum()
    return {int(year): float(totals[year]) for year in totals.index if months_per_year[year] == 12}


def build_annual_shares(daily_df: pd.DataFrame, supply_by_year: dict[int, float]) -> pd.DataFrame:
    """Exchange volume, traded days and share of ESCO annual supply, per year.

    Args:
        daily_df: Validated daily table.
        supply_by_year: Mapping of year to ESCO supply GWh (complete years only).

    Returns:
        DataFrame indexed by year with volume_gwh, traded_days and share_pct
        (NaN when ESCO supply for that year is not available).
    """
    grouped = daily_df.groupby(daily_df["date"].dt.year)
    annual = pd.DataFrame(
        {"volume_gwh": grouped["volume_mwh"].sum() / 1000.0, "traded_days": grouped["date"].size()}
    )
    supply = pd.Series({year: supply_by_year.get(int(year)) for year in annual.index}, dtype="float64")
    annual["share_pct"] = annual["volume_gwh"] / supply * 100.0
    return annual


def build_annual_table(daily_df: pd.DataFrame, supply_by_year: dict[int, float]) -> pd.DataFrame:
    """Display table: volume, traded days and share of ESCO annual supply per year.

    Args:
        daily_df: Validated daily table.
        supply_by_year: Mapping of year to ESCO supply GWh (complete years only).

    Returns:
        Display-ready DataFrame with one row per year.
    """
    annual = build_annual_shares(daily_df, supply_by_year)
    table = pd.DataFrame(
        {
            "Year": annual.index.astype(str),
            "Volume (GWh)": annual["volume_gwh"].round(1).to_numpy(),
            "Traded days": annual["traded_days"].to_numpy(),
            "Share of ESCO annual supply": [
                "n/a" if pd.isna(value) else f"{value:.2f}%" for value in annual["share_pct"]
            ],
        }
    )
    return to_object_dtype(table)


def format_day(timestamp: pd.Timestamp) -> str:
    """Format a timestamp as '24 Jul 2024'.

    Args:
        timestamp: Date to format.

    Returns:
        Day, short month name and year.
    """
    return f"{timestamp.day} {timestamp:%b %Y}"


def build_volume_chart(monthly_df: pd.DataFrame) -> go.Figure:
    """Monthly exchange volume for all 27 months, zero months included.

    Args:
        monthly_df: Validated monthly table.

    Returns:
        Plotly figure with one bar per month on a categorical month axis.
    """
    figure = px.bar(
        monthly_df,
        x="month_display",
        y="volume_gwh",
        custom_data=["days_traded"],
        category_orders={"month_display": monthly_df["month_display"].tolist()},
        labels={"month_display": "Month", "volume_gwh": "GWh"},
        title="Monthly GENEX Day-Ahead Volume, GWh",
    )
    figure.update_traces(
        hovertemplate="%{x}<br>%{y:,.3f} GWh<br>Traded days: %{customdata[0]}<extra></extra>",
        text=["0" if volume == 0 else "" for volume in monthly_df["volume_gwh"]],
        textposition="outside",
        cliponaxis=False,
    )
    figure.update_xaxes(type="category", title_text="Month", tickangle=-45)
    figure.update_yaxes(title_text="GWh")
    return figure


def weighted_price_for_year(daily_df: pd.DataFrame, year: int) -> float:
    """Volume-weighted traded price on GENEX for one calendar year, from the daily file.

    Args:
        daily_df: Validated daily table.
        year: Calendar year.

    Returns:
        Price in GEL/MWh.

    Raises:
        GenexDataError: If the year has no traded volume.
    """
    year_df = daily_df[daily_df["date"].dt.year == year]
    volume = float(year_df["volume_mwh"].sum())
    if volume <= 0:
        raise GenexDataError(f"No traded volume in {year}")
    return float((year_df["volume_mwh"] * year_df["price_gel_per_mwh"]).sum()) / volume


def build_price_chart(monthly_df: pd.DataFrame) -> go.Figure:
    """Monthly traded price on GENEX on the same 27-month axis as the volume chart.

    Months without cleared volume have no dot; no line joins the months.
    Marker size grows with the number of traded days in the month.

    Args:
        monthly_df: Validated monthly table.

    Returns:
        Plotly figure.
    """
    traded = monthly_df["volume_mwh"] > 0
    prices = monthly_df["price_gel_per_mwh"].where(traded)
    max_days = float(monthly_df["days_traded"].max())
    sizes = [
        MARKER_SIZE_MIN + (MARKER_SIZE_MAX - MARKER_SIZE_MIN) * float(days) / max_days if days > 0 else 0.0
        for days in monthly_df["days_traded"]
    ]
    month_labels = monthly_df["month_display"].tolist()

    figure = go.Figure(
        go.Scatter(
            x=month_labels,
            y=prices,
            mode="markers",
            marker={"size": sizes},
            customdata=monthly_df[["days_traded", "volume_gwh"]].to_numpy(),
            hovertemplate=(
                "%{x}<br>%{y:,.2f} GEL/MWh<br>Traded days: %{customdata[0]}"
                "<br>Volume: %{customdata[1]:,.3f} GWh<extra></extra>"
            ),
            name="Traded price on GENEX",
        )
    )
    figure.update_layout(title="Traded Price on GENEX, GEL/MWh (Monthly, Volume-Weighted)", showlegend=False)
    figure.update_xaxes(
        type="category", categoryorder="array", categoryarray=month_labels, title_text="Month", tickangle=-45
    )
    figure.update_yaxes(title_text="GEL/MWh")
    return figure


def read_comparison(path: Path, monthly_df: pd.DataFrame) -> pd.DataFrame:
    """Read and validate the GENEX vs ESCO comparison file (one row per traded month).

    The file must cover exactly the months with cleared volume in the monthly file,
    with the same traded days, volume and GENEX price.

    Args:
        path: Path to genex_vs_esco_monthly.csv.
        monthly_df: Validated monthly table.

    Returns:
        DataFrame sorted by month with month_start, month_label (YYYY-MM key),
        month_display ("Jun 2025") and a boolean representative column.

    Raises:
        GenexDataError: If the file is missing or fails any check.
    """
    label = "GENEX vs ESCO comparison"
    comparison_df = read_csv_checked(path, COMPARISON_COLUMNS, label)

    if len(comparison_df) != EXPECTED_COMPARISON_ROWS:
        raise GenexDataError(f"{label} file: expected {EXPECTED_COMPARISON_ROWS} rows, found {len(comparison_df)}")
    if comparison_df[COMPARISON_COLUMNS].isna().any().any():
        raise GenexDataError(f"{label} file contains empty values")

    comparison_df = to_numeric_checked(comparison_df, COMPARISON_NUMERIC, label)
    flags = comparison_df["representative_month"].astype(str).str.strip()
    if not set(flags).issubset(REPRESENTATIVE_VALUES):
        raise GenexDataError(f"{label} file has unexpected representative_month values")
    comparison_df["representative"] = flags == REPRESENTATIVE_YES

    try:
        comparison_df["month_start"] = pd.to_datetime(
            {"year": comparison_df["year"], "month": comparison_df["month"], "day": 1}
        )
    except (ValueError, TypeError) as exc:
        raise GenexDataError(f"{label} file has invalid year or month values") from exc
    comparison_df = comparison_df.sort_values("month_start").reset_index(drop=True)
    if comparison_df["month_start"].duplicated().any():
        raise GenexDataError(f"{label} file contains duplicate months")

    traded = monthly_df[monthly_df["volume_mwh"] > 0].set_index("month_start")
    if list(traded.index) != list(comparison_df["month_start"]):
        raise GenexDataError(f"{label} file does not cover exactly the traded months")
    reference = traded.loc[comparison_df["month_start"]]
    if (reference["days_traded"].to_numpy() != comparison_df["days_traded"].to_numpy()).any():
        raise GenexDataError(f"{label} file: traded days differ from the monthly file")
    if float(abs(reference["volume_mwh"].to_numpy() - comparison_df["volume_mwh"].to_numpy()).max()) > DAILY_MONTHLY_TOLERANCE_MWH:
        raise GenexDataError(f"{label} file: volumes differ from the monthly file")
    if float(abs(reference["price_gel_per_mwh"].to_numpy() - comparison_df["genex_price_gel_mwh"].to_numpy()).max()) > PRICE_TOLERANCE_GEL:
        raise GenexDataError(f"{label} file: GENEX prices differ from the monthly file")

    gap_check = comparison_df["genex_price_gel_mwh"] - comparison_df["esco_series2_gel_mwh"] - comparison_df["gap_gel_mwh"]
    if float(gap_check.abs().max()) > PRICE_TOLERANCE_GEL:
        raise GenexDataError(f"{label} file: gap is not GENEX minus ESCO")
    pct_check = comparison_df["gap_gel_mwh"] / comparison_df["esco_series2_gel_mwh"] * 100.0 - comparison_df["gap_pct"]
    if float(pct_check.abs().max()) > GAP_PCT_TOLERANCE:
        raise GenexDataError(f"{label} file: gap percentage does not match the gap")

    comparison_df["month_label"] = comparison_df["month_start"].dt.strftime("%Y-%m")
    comparison_df["month_display"] = comparison_df["month_start"].dt.strftime("%b %Y")
    return comparison_df


@st.cache_data
def load_genex_comparison_data(comparison_path_str: str, monthly_path_str: str) -> pd.DataFrame:
    """Load and validate the GENEX vs ESCO comparison file.

    Args:
        comparison_path_str: Path to the comparison file as a string (hashable for the cache).
        monthly_path_str: Path to the monthly file, used for cross-checks.

    Returns:
        Validated comparison table.

    Raises:
        GenexDataError: If a file is missing or fails validation.
    """
    monthly_df = read_monthly(Path(monthly_path_str))
    return to_object_dtype(read_comparison(Path(comparison_path_str), monthly_df))


def summarise_comparison(comparison_df: pd.DataFrame) -> dict[str, float | int | pd.Series]:
    """Headline figures for the comparison KPI cards and data notes.

    Args:
        comparison_df: Validated comparison table.

    Returns:
        Dictionary with months_below, months_total, representative_months,
        mean_gap and mean_gap_pct (simple averages over representative months),
        weighted_gap (volume-weighted over representative months) and
        implied_by_year (implied gross difference in GEL per year).
    """
    representative = comparison_df[comparison_df["representative"].astype(bool)]
    weighted_gap = float((representative["gap_gel_mwh"] * representative["volume_mwh"]).sum()) / float(
        representative["volume_mwh"].sum()
    )
    return {
        "months_below": int((comparison_df["gap_gel_mwh"] < 0).sum()),
        "months_total": int(len(comparison_df)),
        "representative_months": int(len(representative)),
        "mean_gap": float(representative["gap_gel_mwh"].mean()),
        "mean_gap_pct": float(representative["gap_pct"].mean()),
        "weighted_gap": weighted_gap,
        "implied_by_year": comparison_df["saving_gel"].groupby(comparison_df["year"].astype(int)).sum(),
    }


def build_comparison_chart(comparison_df: pd.DataFrame) -> go.Figure:
    """Dumbbell chart: traded price on GENEX and ESCO balancing tariff (sold) per traded month.

    Each traded month has a GENEX dot and an ESCO dot joined by a line. Months with
    fewer than 10 traded days are faded.

    Args:
        comparison_df: Validated comparison table.

    Returns:
        Plotly figure.
    """
    month_labels = comparison_df["month_display"].tolist()
    representative = comparison_df["representative"].astype(bool).tolist()
    opacities = [1.0 if is_representative else FADED_OPACITY for is_representative in representative]

    figure = go.Figure()
    for show_representative in (True, False):
        connector_x: list[str | None] = []
        connector_y: list[float | None] = []
        for row in comparison_df.itertuples(index=False):
            if bool(row.representative) == show_representative:
                connector_x += [row.month_display, row.month_display, None]
                connector_y += [float(row.genex_price_gel_mwh), float(row.esco_series2_gel_mwh), None]
        figure.add_trace(
            go.Scatter(
                x=connector_x,
                y=connector_y,
                mode="lines",
                line={"color": CONNECTOR_COLOUR, "width": 3},
                opacity=1.0 if show_representative else FADED_OPACITY,
                hoverinfo="skip",
                showlegend=False,
            )
        )

    figure.add_trace(
        go.Scatter(
            x=month_labels,
            y=comparison_df["esco_series2_gel_mwh"],
            mode="markers",
            name="ESCO balancing tariff (sold)",
            showlegend=False,
            marker={"color": ESCO_COLOUR, "size": 12, "opacity": opacities},
            hovertemplate="ESCO balancing tariff (sold): %{y:,.2f} GEL/MWh<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=month_labels,
            y=comparison_df["genex_price_gel_mwh"],
            mode="markers",
            name="Traded price on GENEX",
            showlegend=False,
            marker={"color": GENEX_COLOUR, "size": 12, "opacity": opacities},
            customdata=comparison_df[["days_traded", "gap_gel_mwh", "gap_pct"]].to_numpy(),
            hovertemplate=(
                "Traded price on GENEX: %{y:,.2f} GEL/MWh<br>"
                "Gap: %{customdata[1]:,.2f} GEL/MWh (%{customdata[2]:.1f}%)<br>"
                "Traded days: %{customdata[0]}<extra></extra>"
            ),
        )
    )
    # Legend-only entries at full colour: the data traces carry per-month opacity, and
    # Plotly would otherwise draw the legend symbol with the first (faded) month's opacity.
    for legend_name, legend_colour in (
        ("ESCO balancing tariff (sold)", ESCO_COLOUR),
        ("Traded price on GENEX", GENEX_COLOUR),
    ):
        figure.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                name=legend_name,
                marker={"color": legend_colour, "size": 12},
                hoverinfo="skip",
            )
        )
    figure.update_layout(
        title="Traded Price on GENEX vs ESCO Balancing Tariff (Sold), GEL/MWh",
        hovermode="x unified",
        legend={"orientation": "h", "y": -0.3, "x": 0.5, "xanchor": "center", "title": None},
    )
    figure.update_xaxes(
        type="category", categoryorder="array", categoryarray=month_labels, title_text="Traded month", tickangle=-45
    )
    figure.update_yaxes(title_text="GEL/MWh")
    return figure


def build_comparison_table(comparison_df: pd.DataFrame) -> pd.DataFrame:
    """Display table for the comparison, one row per traded month.

    Args:
        comparison_df: Validated comparison table.

    Returns:
        Display-ready DataFrame.
    """
    table = pd.DataFrame(
        {
            "Month": comparison_df["month_display"].to_numpy(),
            "Traded days": comparison_df["days_traded"].astype(int).to_numpy(),
            "Volume (MWh)": comparison_df["volume_mwh"].astype(float).round(1).to_numpy(),
            "Traded price on GENEX (GEL/MWh)": comparison_df["genex_price_gel_mwh"].astype(float).round(2).to_numpy(),
            "ESCO balancing tariff, sold (GEL/MWh)": comparison_df["esco_series2_gel_mwh"].astype(float).round(2).to_numpy(),
            "Gap (GEL/MWh)": comparison_df["gap_gel_mwh"].astype(float).round(2).to_numpy(),
            "Gap (%)": comparison_df["gap_pct"].astype(float).round(1).to_numpy(),
            "Implied gross difference (GEL)": comparison_df["saving_gel"].astype(int).to_numpy(),
            "10+ traded days": ["yes" if flag else "no" for flag in comparison_df["representative"].astype(bool)],
        }
    )
    return to_object_dtype(table)


def render_comparison(comparison_df: pd.DataFrame, summary: dict[str, float | int | pd.Series]) -> None:
    """Render the GENEX vs ESCO comparison: KPI cards, dumbbell chart, table and caption.

    Card values are kept short because st.metric truncates long values with an
    ellipsis; supporting figures go in a grey line under the value (no arrow, no
    colour) and in the hover tooltip.

    Args:
        comparison_df: Validated comparison table.
        summary: Output of summarise_comparison.
    """
    st.subheader("Traded price vs ESCO balancing tariff (sold)")

    implied_2025 = float(summary["implied_by_year"].get(2025, 0.0))
    below_column, gap_column, implied_column = st.columns(3)
    below_column.metric(
        "GENEX below ESCO (traded months)",
        f"{summary['months_below']} of {summary['months_total']}",
        border=True,
        help="Months with cleared volume on GENEX where the traded price was below ESCO's balancing tariff (sold).",
    )
    gap_column.metric(
        "Average gap, months with 10+ traded days",
        f"{summary['mean_gap']:.1f} GEL/MWh",
        delta=f"{summary['mean_gap_pct']:.1f}% vs same-month ESCO tariff",
        delta_color="off",
        delta_arrow="off",
        border=True,
        help=(
            "Each month's traded price on GENEX is compared with ESCO's balancing tariff (sold) for the "
            f"same month. Simple average over the {summary['representative_months']} months with 10 or "
            "more traded days."
        ),
    )
    implied_column.metric(
        "Implied gross difference 2025 (volume × gap)",
        f"GEL {implied_2025 / 1e6:.2f} million",
        border=True,
        help="Volume × gap, summed over the traded months of 2025. Not net of costs or risks.",
    )

    st.plotly_chart(build_comparison_chart(comparison_df), width="stretch")
    st.dataframe(build_comparison_table(comparison_df), width="stretch", hide_index=True)
    st.caption(
        "Gap = traded price on GENEX minus ESCO balancing tariff (sold, Series 2). Different products: "
        "GENEX clears day-ahead by the hour; ESCO's figure is a regulated monthly settlement tariff. "
        "Descriptive only. Implied gross difference = volume × gap, not net of costs or risks. GEL. "
        "Faded = fewer than 10 traded days. ESCO 2026 values from ESCO's published tariff page."
    )


def render_kpis(daily_df: pd.DataFrame, monthly_df: pd.DataFrame) -> None:
    """Render the four headline cards.

    Args:
        daily_df: Validated daily table.
        monthly_df: Validated monthly table.
    """
    total_column, days_column, first_column, last_column = st.columns(4)
    total_column.metric("Total traded", f"{monthly_df['volume_gwh'].sum():,.1f} GWh", border=True)
    days_column.metric("Traded days", f"{len(daily_df):,}", border=True)
    first_column.metric("First trade", format_day(daily_df["date"].min()), border=True)
    last_column.metric("Last trade", format_day(daily_df["date"].max()), border=True)


def render_data_notes(summary: dict[str, float | int | pd.Series] | None) -> None:
    """Render the data-notes expander for the whole section.

    Args:
        summary: Output of summarise_comparison, or None if the comparison
            could not be loaded (its notes are then left out).
    """
    with st.expander("Data notes"):
        st.markdown(
            """
- **Currency.** Prices are in GEL. The EUR and USD columns in the export are not used:
  they are zero on 3 traded days while the GEL price is positive.
- **29 March 2026** has 23 traded hours, not 24.
- **Share of supply** uses ESCO supply data, which is available up to December 2025.
  2026 is therefore shown as n/a.
- **Overlap with the Balancing Supply page.** ESCO's non-balancing volume includes
  exchange sales from mid-2024, so exchange volume is part of the non-balancing
  volume in the "supply by seller category" section.
"""
        )
        if summary is not None:
            st.markdown(
                f"""
- **July 2024 ESCO tariff** uses the corrected decimal (156.16 GEL/MWh); ESCO published it
  with a comma as the decimal separator.
- **ESCO 2026 values** come from ESCO's published tariff page. The repository's ESCO tariff
  files cover 2022-2025.
- **Average gap.** Simple average over the {summary['representative_months']} months with 10 or
  more traded days. Weighted by volume, the same months give {summary['weighted_gap']:.1f} GEL/MWh.
"""
            )


def render_genex_exchange_section() -> None:
    """Render the GENEX exchange section (volume, traded price and ESCO comparison).

    On any data problem it shows a plain error message inside the section and
    returns, so the rest of the page still renders.
    """
    try:
        daily_df, monthly_df = load_genex_volume_data(str(DAILY_FILE), str(MONTHLY_FILE))
    except GenexDataError as exc:
        logger.error("GENEX exchange data could not be loaded: %s", exc)
        st.error(f"GENEX exchange data could not be loaded: {exc}.")
        return
    except Exception:  # UI boundary: a failure here must never take the page down
        logger.exception("Unexpected error loading GENEX exchange data")
        st.error("GENEX exchange data could not be loaded because of an unexpected error.")
        return

    st.subheader("Cleared volume")
    render_kpis(daily_df, monthly_df)

    st.plotly_chart(build_volume_chart(monthly_df), width="stretch")
    st.caption(
        "GENEX day-ahead export (transitional market model). Volume = cleared energy summed "
        "over hours, MWh. Zero = no cleared volume in the export, not necessarily an outage. "
        "Shown: Jul 2024 (market opened 1 Jul 2024; first cleared trade 24 Jul) to Sep 2026; "
        "Oct 2026 excluded (export partly padded). Unit assumed MWh."
    )

    st.markdown("#### Volume by year")
    st.dataframe(build_annual_table(daily_df, load_annual_supply_gwh()), width="stretch", hide_index=True)
    st.caption(
        "Share = exchange volume in the year divided by ESCO's total supply in the same year "
        "(supply data available to December 2025)."
    )

    st.subheader("Traded price")
    st.plotly_chart(build_price_chart(monthly_df), width="stretch")
    st.caption(
        "Each dot is one month: the volume-weighted price of all cleared hours in that month. "
        "Dot size = number of traded days. Thin market; months with few trading days are "
        "weakly representative. GEL only."
    )

    summary: dict[str, float | int | pd.Series] | None = None
    try:
        comparison_df = load_genex_comparison_data(str(COMPARISON_FILE), str(MONTHLY_FILE))
        summary = summarise_comparison(comparison_df)
    except GenexDataError as exc:
        logger.error("GENEX vs ESCO comparison could not be loaded: %s", exc)
        st.error(f"GENEX vs ESCO comparison could not be loaded: {exc}.")
    except Exception:  # UI boundary: the rest of the section must still render
        logger.exception("Unexpected error loading the GENEX vs ESCO comparison")
        st.error("GENEX vs ESCO comparison could not be loaded because of an unexpected error.")
    else:
        render_comparison(comparison_df, summary)

    render_data_notes(summary)


def run_acceptance_check() -> bool:
    """Compare the loaded data against the agreed acceptance numbers and log the result.

    Returns:
        True if every number matches, False otherwise.
    """
    try:
        daily_df = read_daily(DAILY_FILE)
        monthly_df = read_monthly(MONTHLY_FILE)
        check_daily_monthly_consistency(daily_df, monthly_df)
    except GenexDataError as exc:
        logger.error("Validation failed: %s", exc)
        return False

    logger.info("Validation passed: %d daily rows, %d monthly rows", len(daily_df), len(monthly_df))
    mismatches = 0

    def report(name: str, expected: object, actual: object, ok: bool) -> None:
        nonlocal mismatches
        mismatches += 0 if ok else 1
        logger.log(logging.INFO if ok else logging.ERROR, "%s: expected %s | actual %s | %s",
                   name, expected, actual, "OK" if ok else "MISMATCH")

    annual = build_annual_shares(daily_df, load_annual_supply_gwh())
    for year, expected in ACCEPTANCE_VOLUME_MWH.items():
        actual = round(float(annual.loc[year, "volume_gwh"]) * 1000.0, 1)
        report(f"{year} volume MWh", expected, actual, abs(actual - expected) < 0.051)
    for year, expected in ACCEPTANCE_TRADED_DAYS.items():
        actual = int(annual.loc[year, "traded_days"])
        report(f"{year} traded days", expected, actual, actual == expected)

    total_gwh = round(float(monthly_df["volume_gwh"].sum()), 2)
    report("total GWh", ACCEPTANCE_TOTAL_GWH, total_gwh, abs(total_gwh - ACCEPTANCE_TOTAL_GWH) < 0.0051)

    with_volume = int((monthly_df["volume_mwh"] > 0).sum())
    months = (len(monthly_df), with_volume, len(monthly_df) - with_volume)
    report("months total/with volume/without", ACCEPTANCE_MONTHS, months, months == ACCEPTANCE_MONTHS)

    top = monthly_df.nlargest(3, "volume_gwh")[["month_label", "volume_gwh"]]
    actual_top = [(row.month_label, round(float(row.volume_gwh), 3)) for row in top.itertuples()]
    report("largest months GWh", ACCEPTANCE_LARGEST_GWH, actual_top, actual_top == ACCEPTANCE_LARGEST_GWH)

    for year, expected in ACCEPTANCE_SHARE_PCT.items():
        actual = round(float(annual.loc[year, "share_pct"]), 2)
        report(f"{year} share of ESCO supply %", expected, actual, abs(actual - expected) < 1e-9)
    report("2026 share of ESCO supply", "n/a", "n/a" if pd.isna(annual.loc[2026, "share_pct"]) else "value",
           bool(pd.isna(annual.loc[2026, "share_pct"])))

    first_trade, last_trade = format_day(daily_df["date"].min()), format_day(daily_df["date"].max())
    report("first / last trade", ("24 Jul 2024", "29 Jun 2026"), (first_trade, last_trade),
           (first_trade, last_trade) == ("24 Jul 2024", "29 Jun 2026"))

    prices = monthly_df.set_index("month_label")["price_gel_per_mwh"]
    for label, expected in ACCEPTANCE_PRICE_GEL_PER_MWH.items():
        actual = round(float(prices.loc[label]), 2)
        report(f"{label} traded price GEL/MWh", expected, actual, abs(actual - expected) < 1e-9)
    weighted_2025 = round(weighted_price_for_year(daily_df, 2025), 2)
    report("2025 volume-weighted price GEL/MWh", ACCEPTANCE_WEIGHTED_PRICE_2025, weighted_2025,
           abs(weighted_2025 - ACCEPTANCE_WEIGHTED_PRICE_2025) < 1e-9)

    try:
        comparison_df = read_comparison(COMPARISON_FILE, monthly_df)
    except GenexDataError as exc:
        logger.error("Comparison validation failed: %s", exc)
        return False
    summary = summarise_comparison(comparison_df)
    report("comparison rows", EXPECTED_COMPARISON_ROWS, len(comparison_df), len(comparison_df) == EXPECTED_COMPARISON_ROWS)
    report("GENEX below ESCO (months)", "13 of 13", f"{summary['months_below']} of {summary['months_total']}",
           (summary["months_below"], summary["months_total"]) == (13, 13))
    gaps = comparison_df.set_index("month_label")["gap_gel_mwh"]
    for label, expected in ACCEPTANCE_GAP_GEL_PER_MWH.items():
        actual = round(float(gaps.loc[label]), 2)
        report(f"{label} gap GEL/MWh", expected, actual, abs(actual - expected) < 1e-9)
    for year, expected in ACCEPTANCE_IMPLIED_GEL_BY_YEAR.items():
        actual = int(summary["implied_by_year"].get(year, 0))
        report(f"{year} implied gross difference GEL", expected, actual, abs(actual - expected) <= 1)
    representative = (summary["representative_months"], round(summary["mean_gap"], 1), round(summary["mean_gap_pct"], 1))
    report("representative months / mean gap / mean gap %", ACCEPTANCE_REPRESENTATIVE, representative,
           representative == ACCEPTANCE_REPRESENTATIVE)

    logger.info("Acceptance check: %s", "ALL MATCH" if mismatches == 0 else f"{mismatches} MISMATCHES")
    return mismatches == 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    sys.exit(0 if run_acceptance_check() else 1)