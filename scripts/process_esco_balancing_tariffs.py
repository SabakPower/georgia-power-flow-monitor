"""Process raw ESCO balancing electricity tariff tables into clean monthly files.

Reads the two wide-format raw tables transcribed from the ESCO website, converts
them to long format, corrects decimal-separator defects with a logged record of
every correction, converts tetri/kWh to GEL/MWh, validates the result and writes
one clean CSV per series to data/processed/esco/.

These are regulated ESCO settlement tariffs. They are NOT market prices.

Usage:
    python scripts/process_esco_balancing_tariffs.py
"""

from __future__ import annotations

import logging
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

REPO_ROOT: Path = Path(__file__).resolve().parents[1]
RAW_DIR: Path = REPO_ROOT / "data" / "raw" / "esco"
PROCESSED_DIR: Path = REPO_ROOT / "data" / "processed" / "esco"

EXPECTED_YEARS: tuple[int, ...] = (2022, 2023, 2024, 2025)
EXPECTED_ROW_COUNT: int = len(EXPECTED_YEARS) * 12
TETRI_PER_KWH_TO_GEL_PER_MWH: float = 10.0

MONTH_NAME_TO_NUMBER: dict[str, int] = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}

OUTPUT_COLUMNS: list[str] = [
    "date",
    "year",
    "month_number",
    "month",
    "tariff_tetri_per_kwh",
    "tariff_gel_per_mwh",
]

logger: logging.Logger = logging.getLogger("process_esco_balancing_tariffs")


@dataclass(frozen=True)
class TariffSeries:
    """Definition of one ESCO balancing electricity tariff series.

    Attributes:
        name: Short identifier used in log messages.
        description: Human-readable description of the regulated tariff.
        raw_path: Path to the raw wide-format CSV (read-only input).
        output_path: Path of the clean long-format CSV to write.
        known_defects: (year, month_number) pairs where a decimal-separator
            defect is documented in data/raw/esco/SOURCE.md.
    """

    name: str
    description: str
    raw_path: Path
    output_path: Path
    known_defects: tuple[tuple[int, int], ...] = ()


def build_series_definitions() -> list[TariffSeries]:
    """Return the definitions of the two ESCO balancing tariff series.

    Returns:
        List of TariffSeries, one per raw input file.
    """
    return [
        TariffSeries(
            name="sold",
            description="Weighted average tariff of balancing electricity sold by ESCO",
            raw_path=RAW_DIR / "balancing_price_sold_wide.csv",
            output_path=PROCESSED_DIR / "balancing_tariff_sold_monthly_clean.csv",
            known_defects=((2024, 7),),
        ),
        TariffSeries(
            name="purchased_small_plants",
            description=(
                "Tariff of balancing electricity purchased by ESCO from "
                "small-capacity deregulated power plants"
            ),
            raw_path=RAW_DIR / "balancing_price_purchased_small_plants_wide.csv",
            output_path=(
                PROCESSED_DIR / "balancing_tariff_purchased_small_plants_monthly_clean.csv"
            ),
        ),
    ]


def read_raw_wide(path: Path) -> pd.DataFrame:
    """Read a raw wide-format tariff CSV with every value kept as text.

    Values are read as strings so that each one is parsed explicitly later,
    instead of pandas guessing column types around malformed cells.

    Args:
        path: Path to the raw CSV.

    Returns:
        DataFrame with columns month, 2022, 2023, 2024, 2025, all strings,
        with surrounding whitespace removed.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is empty, unparseable, not UTF-8, or has
            unexpected columns.
    """
    try:
        wide_df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Raw tariff file not found: {path}") from exc
    except pd.errors.EmptyDataError as exc:
        raise ValueError(f"Raw tariff file is empty: {path}") from exc
    except pd.errors.ParserError as exc:
        raise ValueError(f"Could not parse raw tariff file {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"Raw tariff file is not valid UTF-8: {path}") from exc

    wide_df.columns = [str(column).strip() for column in wide_df.columns]
    expected_columns = ["month", *[str(year) for year in EXPECTED_YEARS]]
    if list(wide_df.columns) != expected_columns:
        raise ValueError(
            f"Unexpected columns in {path.name}: {list(wide_df.columns)}; "
            f"expected {expected_columns}"
        )

    return wide_df.apply(lambda column: column.str.strip())


def wide_to_long(wide_df: pd.DataFrame, series_name: str) -> pd.DataFrame:
    """Reshape a wide tariff table (months x years) into one row per month.

    Args:
        wide_df: Wide DataFrame as returned by read_raw_wide.
        series_name: Series identifier for error messages.

    Returns:
        DataFrame with columns month, year (int), raw_value (str),
        month_number (int).

    Raises:
        ValueError: If a month name is not recognised.
    """
    long_df = wide_df.melt(id_vars="month", var_name="year", value_name="raw_value")
    long_df["year"] = long_df["year"].astype(int)

    unknown_months = sorted(set(long_df["month"]) - set(MONTH_NAME_TO_NUMBER))
    if unknown_months:
        raise ValueError(f"[{series_name}] Unrecognised month names: {unknown_months}")

    long_df["month_number"] = long_df["month"].map(MONTH_NAME_TO_NUMBER).astype(int)
    return long_df


def parse_tariff_value(raw_value: str, series_name: str, year: int, month: str) -> tuple[float, bool]:
    """Convert one raw tariff string to a float, correcting a comma decimal.

    A value containing exactly one comma and no period is treated as a comma
    decimal separator and corrected. Any other malformed value is rejected.

    Args:
        raw_value: Value as transcribed in the raw file.
        series_name: Series identifier for error messages.
        year: Calendar year of the value.
        month: Month name of the value.

    Returns:
        Tuple of (parsed value in tetri/kWh, whether a correction was applied).

    Raises:
        ValueError: If the value is empty, ambiguous, non-numeric or not finite.
    """
    value = raw_value.strip()
    if value == "":
        raise ValueError(f"[{series_name}] Missing value for {month} {year}")

    corrected = False
    if "," in value:
        if "." in value or value.count(",") != 1:
            raise ValueError(
                f"[{series_name}] Ambiguous number format '{raw_value}' for {month} {year}"
            )
        value = value.replace(",", ".")
        corrected = True

    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(
            f"[{series_name}] Non-numeric value '{raw_value}' for {month} {year}"
        ) from exc

    if not math.isfinite(parsed):
        raise ValueError(f"[{series_name}] Non-finite value '{raw_value}' for {month} {year}")

    return parsed, corrected


def parse_tariff_values(long_df: pd.DataFrame, series_name: str) -> tuple[pd.DataFrame, list[tuple[int, int]]]:
    """Parse every raw value in a long tariff table, logging each correction.

    Args:
        long_df: Long DataFrame as returned by wide_to_long.
        series_name: Series identifier for log and error messages.

    Returns:
        Tuple of (DataFrame with a numeric tariff_tetri_per_kwh column,
        list of (year, month_number) pairs that were corrected).
    """
    parsed_values: list[float] = []
    corrections: list[tuple[int, int]] = []

    for row in long_df.itertuples(index=False):
        parsed, corrected = parse_tariff_value(row.raw_value, series_name, row.year, row.month)
        parsed_values.append(parsed)
        if corrected:
            corrections.append((row.year, row.month_number))
            logger.warning(
                "[%s] Corrected comma decimal separator for %s %d: '%s' -> %s",
                series_name,
                row.month,
                row.year,
                row.raw_value,
                parsed,
            )

    parsed_df = long_df.copy()
    parsed_df["tariff_tetri_per_kwh"] = parsed_values
    return parsed_df, corrections


def build_clean_frame(parsed_df: pd.DataFrame) -> pd.DataFrame:
    """Add date and GEL/MWh columns and return the final column layout.

    Args:
        parsed_df: DataFrame with year, month_number, month and
            tariff_tetri_per_kwh columns.

    Returns:
        DataFrame with OUTPUT_COLUMNS, sorted by date. GEL/MWh is rounded to
        6 decimals (lossless relative to source precision).
    """
    clean_df = parsed_df.copy()
    clean_df["date"] = pd.to_datetime(
        {"year": clean_df["year"], "month": clean_df["month_number"], "day": 1}
    )
    # Source precision is at most 7 decimals in tetri/kWh, so 6 decimals in GEL/MWh
    # is lossless; rounding only removes floating-point noise from the * 10 step.
    clean_df["tariff_gel_per_mwh"] = (
        clean_df["tariff_tetri_per_kwh"] * TETRI_PER_KWH_TO_GEL_PER_MWH
    ).round(6)
    return clean_df[OUTPUT_COLUMNS].sort_values("date").reset_index(drop=True)


def validate_clean_frame(clean_df: pd.DataFrame, series_name: str) -> None:
    """Run structural checks on a clean tariff table before it is written.

    Args:
        clean_df: DataFrame as returned by build_clean_frame.
        series_name: Series identifier for error messages.

    Raises:
        ValueError: Listing every failed check, if any check fails.
    """
    failures: list[str] = []

    if len(clean_df) != EXPECTED_ROW_COUNT:
        failures.append(f"expected {EXPECTED_ROW_COUNT} rows, found {len(clean_df)}")

    found_years = sorted(clean_df["year"].unique().tolist())
    if found_years != list(EXPECTED_YEARS):
        failures.append(f"expected years {list(EXPECTED_YEARS)}, found {found_years}")

    for year, group in clean_df.groupby("year"):
        months = sorted(group["month_number"].tolist())
        if months != list(range(1, 13)):
            failures.append(f"year {year} does not contain exactly months 1-12: {months}")

    duplicate_count = int(clean_df.duplicated(subset=["year", "month_number"]).sum())
    if duplicate_count:
        failures.append(f"{duplicate_count} duplicate (year, month_number) rows")

    if clean_df[OUTPUT_COLUMNS].isna().any().any():
        failures.append("null values present")

    non_positive = clean_df[clean_df["tariff_tetri_per_kwh"] <= 0]
    if not non_positive.empty:
        failures.append(f"{len(non_positive)} tariff values are zero or negative")

    if failures:
        raise ValueError(f"[{series_name}] Validation failed: " + "; ".join(failures))


def write_clean_frame(clean_df: pd.DataFrame, output_path: Path) -> None:
    """Write a clean tariff table to CSV with dates as YYYY-MM-DD.

    Args:
        clean_df: DataFrame to write.
        output_path: Destination path; parent folders are created if needed.

    Raises:
        OSError: If the file cannot be written.
    """
    output_df = clean_df.copy()
    output_df["date"] = output_df["date"].dt.strftime("%Y-%m-%d")
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_df.to_csv(output_path, index=False, encoding="utf-8")
    except OSError as exc:
        raise OSError(f"Could not write clean tariff file {output_path}: {exc}") from exc


def check_known_defects(series: TariffSeries, corrections: list[tuple[int, int]]) -> None:
    """Compare the corrections applied against the defects documented in SOURCE.md.

    Logs a WARNING if a documented defect was not found (the source may have
    changed) or if a correction was applied that is not documented.

    Args:
        series: Series definition including its documented defects.
        corrections: (year, month_number) pairs corrected during parsing.
    """
    applied = set(corrections)
    documented = set(series.known_defects)

    for year, month_number in sorted(documented - applied):
        logger.warning(
            "[%s] Documented defect for %d-%02d was NOT found; the source may have changed",
            series.name,
            year,
            month_number,
        )

    for year, month_number in sorted(applied - documented):
        logger.warning(
            "[%s] Correction applied for %d-%02d is not documented in SOURCE.md",
            series.name,
            year,
            month_number,
        )


def process_series(series: TariffSeries) -> pd.DataFrame:
    """Read, reshape, parse, convert and validate one tariff series.

    Args:
        series: Series definition.

    Returns:
        Validated clean DataFrame ready to be written.
    """
    logger.info("[%s] Reading %s", series.name, series.raw_path.relative_to(REPO_ROOT))
    wide_df = read_raw_wide(series.raw_path)
    long_df = wide_to_long(wide_df, series.name)
    parsed_df, corrections = parse_tariff_values(long_df, series.name)
    check_known_defects(series, corrections)
    clean_df = build_clean_frame(parsed_df)
    validate_clean_frame(clean_df, series.name)
    logger.info("[%s] Validation passed (%d rows)", series.name, len(clean_df))
    return clean_df


def main() -> int:
    """Process all tariff series; write outputs only if every series is valid.

    Returns:
        Process exit code: 0 on success, 1 on any failure.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    series_list = build_series_definitions()

    try:
        results: list[tuple[TariffSeries, pd.DataFrame]] = [
            (series, process_series(series)) for series in series_list
        ]
        for series, clean_df in results:
            write_clean_frame(clean_df, series.output_path)
            logger.info(
                "[%s] Wrote %s | rows: %d | coverage: %s to %s",
                series.name,
                series.output_path.relative_to(REPO_ROOT),
                len(clean_df),
                clean_df["date"].min().strftime("%Y-%m"),
                clean_df["date"].max().strftime("%Y-%m"),
            )
    except (FileNotFoundError, ValueError, OSError) as exc:
        logger.error("Processing failed: %s", exc)
        return 1

    logger.info("All ESCO balancing tariff series processed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())