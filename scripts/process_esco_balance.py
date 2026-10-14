"""Process the raw ESCO electricity balance into the clean monthly dataset.

Reads data/raw/esco/electricity_balance_monthly.csv (never modified), cleans
rounding artefacts, adds a date column and derived indicators, corrects known
source-metadata defects with a logged record of every correction, and writes
data/processed/esco/electricity_balance_monthly_clean.csv, which the dashboard
and downstream joins read.

The electricity balance contains energy volumes in million kWh. It is not
tariff or market data.

Usage:
    python scripts/process_esco_balance.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT: Path = Path(__file__).resolve().parents[1]
INPUT_FILE: Path = REPO_ROOT / "data" / "raw" / "esco" / "electricity_balance_monthly.csv"
OUTPUT_FILE: Path = REPO_ROOT / "data" / "processed" / "esco" / "electricity_balance_monthly_clean.csv"

REQUIRED_COLUMNS: list[str] = [
    "year",
    "month_number",
    "generation_mln_kwh",
    "hydro_mln_kwh",
    "thermal_mln_kwh",
    "wind_mln_kwh",
    "other_generation_mln_kwh",
    "import_mln_kwh",
    "export_mln_kwh",
    "total_demand_including_losses_mln_kwh",
    "transportation_expenses_mln_kwh",
    "source_url",
]

# Values with an absolute size below this are rounding artefacts (e.g. -0.0001)
# and are set to exactly 0.
NEGATIVE_ZERO_THRESHOLD: float = 0.0005

# Known source-metadata defects in the raw file. The raw file is never edited;
# corrections are applied here and logged on every run.
# Keyed by year: (value found in the raw file, verified correct value).
SOURCE_URL_CORRECTIONS: dict[int, tuple[str, str]] = {
    2024: (
        "PASTE_ESCO_2024_URL_HERE",
        "https://esco.ge/en/energy-balance/by-year-1/elektroenergiis-balansi-2024",
    ),
}

# Every source_url in the output must point to the ESCO website.
VALID_SOURCE_URL_PREFIX: str = "https://esco.ge/"

logger: logging.Logger = logging.getLogger("process_esco_balance")


def read_raw_balance(path: Path) -> pd.DataFrame:
    """Read the raw ESCO electricity balance CSV.

    Args:
        path: Path to the raw CSV.

    Returns:
        Raw balance DataFrame.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is empty, unparseable, not UTF-8, or missing
            required columns.
    """
    try:
        balance_df = pd.read_csv(path, encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Raw electricity balance file not found: {path}") from exc
    except pd.errors.EmptyDataError as exc:
        raise ValueError(f"Raw electricity balance file is empty: {path}") from exc
    except pd.errors.ParserError as exc:
        raise ValueError(f"Could not parse raw electricity balance file {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"Raw electricity balance file is not valid UTF-8: {path}") from exc

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in balance_df.columns]
    if missing_columns:
        raise ValueError(f"Raw electricity balance is missing required columns: {missing_columns}")

    return balance_df


def clean_rounding_artefacts(balance_df: pd.DataFrame) -> pd.DataFrame:
    """Round numeric columns to 3 decimals and set near-zero artefacts to 0.

    The source publishes volumes to 3 decimals, so rounding to 3 decimals
    removes only floating-point noise.

    Args:
        balance_df: Raw balance DataFrame.

    Returns:
        DataFrame with cleaned numeric columns.
    """
    cleaned_df = balance_df.copy()
    numeric_columns = cleaned_df.select_dtypes(include="number").columns
    cleaned_df[numeric_columns] = cleaned_df[numeric_columns].round(3)
    cleaned_df[numeric_columns] = cleaned_df[numeric_columns].mask(
        cleaned_df[numeric_columns].abs() < NEGATIVE_ZERO_THRESHOLD, 0
    )
    return cleaned_df


def add_date_column(balance_df: pd.DataFrame) -> pd.DataFrame:
    """Add a first-of-month date column built from year and month_number.

    Args:
        balance_df: Balance DataFrame with year and month_number columns.

    Returns:
        DataFrame with an added date column.

    Raises:
        ValueError: If any year/month combination is not a valid date.
    """
    dated_df = balance_df.copy()
    try:
        dated_df["date"] = pd.to_datetime(
            dated_df["year"].astype(str) + "-" + dated_df["month_number"].astype(str) + "-01"
        )
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Could not build dates from year and month_number: {exc}") from exc
    return dated_df


def add_indicators(balance_df: pd.DataFrame) -> pd.DataFrame:
    """Add derived indicators used by the dashboard.

    Note: import_dependency_pct uses GROSS imports over total demand including
    losses. It is not the net import position (imports minus exports).

    Args:
        balance_df: Cleaned, dated balance DataFrame.

    Returns:
        DataFrame with indicator columns added.
    """
    indicators_df = balance_df.copy()

    indicators_df["net_imports_mln_kwh"] = indicators_df["import_mln_kwh"] - indicators_df["export_mln_kwh"]

    indicators_df["hydro_share_pct"] = (
        indicators_df["hydro_mln_kwh"] / indicators_df["generation_mln_kwh"] * 100
    ).round(2)

    indicators_df["thermal_share_pct"] = (
        indicators_df["thermal_mln_kwh"] / indicators_df["generation_mln_kwh"] * 100
    ).round(2)

    indicators_df["wind_share_pct"] = (
        indicators_df["wind_mln_kwh"] / indicators_df["generation_mln_kwh"] * 100
    ).round(2)

    indicators_df["other_generation_share_pct"] = (
        indicators_df["other_generation_mln_kwh"] / indicators_df["generation_mln_kwh"] * 100
    ).round(2)

    indicators_df["import_dependency_pct"] = (
        indicators_df["import_mln_kwh"] / indicators_df["total_demand_including_losses_mln_kwh"] * 100
    ).round(2)

    indicators_df["export_share_of_generation_pct"] = (
        indicators_df["export_mln_kwh"] / indicators_df["generation_mln_kwh"] * 100
    ).round(2)

    indicators_df["transportation_expenses_share_pct"] = (
        indicators_df["transportation_expenses_mln_kwh"]
        / indicators_df["total_demand_including_losses_mln_kwh"]
        * 100
    ).round(2)

    return indicators_df


def correct_source_urls(balance_df: pd.DataFrame) -> pd.DataFrame:
    """Replace documented placeholder source URLs with verified URLs.

    Logs a WARNING for every correction applied, and a WARNING if a documented
    defect is no longer present (the raw file may have changed).

    Args:
        balance_df: Balance DataFrame with a source_url column.

    Returns:
        DataFrame with corrected source_url values.
    """
    corrected_df = balance_df.copy()

    for year, (placeholder, verified_url) in SOURCE_URL_CORRECTIONS.items():
        defect_rows = (corrected_df["year"] == year) & (corrected_df["source_url"] == placeholder)
        defect_count = int(defect_rows.sum())

        if defect_count == 0:
            logger.warning(
                "Documented source_url defect for %d was NOT found; the raw file may have changed",
                year,
            )
            continue

        corrected_df.loc[defect_rows, "source_url"] = verified_url
        logger.warning(
            "Corrected placeholder source_url for %d (%d rows): '%s' -> %s",
            year,
            defect_count,
            placeholder,
            verified_url,
        )

    return corrected_df


def check_source_urls(balance_df: pd.DataFrame) -> None:
    """Fail if any source_url is missing or does not point to the ESCO website.

    Args:
        balance_df: Balance DataFrame after URL corrections.

    Raises:
        ValueError: Listing the affected years, if any URL is invalid.
    """
    source_urls = balance_df["source_url"].astype(str)
    invalid_rows = balance_df.loc[~source_urls.str.startswith(VALID_SOURCE_URL_PREFIX)]
    if not invalid_rows.empty:
        invalid_years = sorted(invalid_rows["year"].unique().tolist())
        raise ValueError(
            f"{len(invalid_rows)} rows have an invalid source_url (years {invalid_years}); "
            f"every source_url must start with {VALID_SOURCE_URL_PREFIX}"
        )


def write_output(balance_df: pd.DataFrame, path: Path) -> None:
    """Write the processed balance dataset to CSV.

    Args:
        balance_df: Fully processed balance DataFrame.
        path: Destination path; parent folders are created if needed.

    Raises:
        OSError: If the file cannot be written.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        balance_df.to_csv(path, index=False)
    except OSError as exc:
        raise OSError(f"Could not write processed electricity balance {path}: {exc}") from exc


def main() -> int:
    """Run the full electricity balance processing pipeline.

    Returns:
        Process exit code: 0 on success, 1 on any failure.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        balance_df = read_raw_balance(INPUT_FILE)
        balance_df = clean_rounding_artefacts(balance_df)
        balance_df = add_date_column(balance_df)
        balance_df = add_indicators(balance_df)
        balance_df = correct_source_urls(balance_df)
        check_source_urls(balance_df)
        write_output(balance_df, OUTPUT_FILE)
    except (FileNotFoundError, ValueError, OSError) as exc:
        logger.error("Processing failed: %s", exc)
        return 1

    logger.info(
        "Processed ESCO electricity balance written | rows: %d | columns: %d | output: %s",
        len(balance_df),
        len(balance_df.columns),
        OUTPUT_FILE.relative_to(REPO_ROOT),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())