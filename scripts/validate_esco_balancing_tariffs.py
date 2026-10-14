"""Validate the clean ESCO balancing electricity tariff files.

Runs two classes of check on the outputs of process_esco_balancing_tariffs.py:

- Hard failures: structural errors that make the data unusable. Logged at
  ERROR level; the script exits with status 1 so the pipeline stops.
- Anomaly flags: values that look unusual and need a human judgement (real
  signal or data error). Logged at WARNING level; they do not stop the pipeline.

These are regulated ESCO settlement tariffs. They are NOT market prices.

Usage:
    python scripts/validate_esco_balancing_tariffs.py
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT: Path = Path(__file__).resolve().parents[1]
PROCESSED_DIR: Path = REPO_ROOT / "data" / "processed" / "esco"

REQUIRED_COLUMNS: list[str] = [
    "date",
    "year",
    "month_number",
    "month",
    "tariff_tetri_per_kwh",
    "tariff_gel_per_mwh",
]
NUMERIC_COLUMNS: list[str] = ["year", "month_number", "tariff_tetri_per_kwh", "tariff_gel_per_mwh"]

EXPECTED_YEARS: tuple[int, ...] = (2022, 2023, 2024, 2025)
EXPECTED_ROW_COUNT: int = len(EXPECTED_YEARS) * 12
TETRI_PER_KWH_TO_GEL_PER_MWH: float = 10.0

# GEL/MWh is rounded to 6 decimals during processing, so the conversion check
# must allow for up to 5e-7 of rounding difference.
CONVERSION_TOLERANCE: float = 1e-6

# A month-on-month move larger than this fraction is flagged for review.
MONTH_ON_MONTH_THRESHOLD: float = 0.30

# Tukey fences at 3.0 x IQR flag only extreme values ("far out" outliers).
IQR_MULTIPLIER: float = 3.0

logger: logging.Logger = logging.getLogger("validate_esco_balancing_tariffs")


@dataclass(frozen=True)
class ValidationTarget:
    """Definition of one clean tariff file to validate.

    Attributes:
        name: Short identifier used in log messages.
        path: Path to the clean CSV.
        fixed_summer_months: Month numbers in which the tariff is expected to
            be a single fixed value within each year. Empty if not applicable.
    """

    name: str
    path: Path
    fixed_summer_months: tuple[int, ...] = ()


@dataclass
class ValidationReport:
    """Collected results of validating one tariff file.

    Attributes:
        hard_failures: Messages for checks that make the data unusable.
        anomaly_flags: Messages for unusual values that need human review.
    """

    hard_failures: list[str] = field(default_factory=list)
    anomaly_flags: list[str] = field(default_factory=list)


def build_validation_targets() -> list[ValidationTarget]:
    """Return the two clean tariff files to validate.

    Returns:
        List of ValidationTarget definitions.
    """
    return [
        ValidationTarget(
            name="sold",
            path=PROCESSED_DIR / "balancing_tariff_sold_monthly_clean.csv",
        ),
        ValidationTarget(
            name="purchased_small_plants",
            path=PROCESSED_DIR / "balancing_tariff_purchased_small_plants_monthly_clean.csv",
            fixed_summer_months=(5, 6, 7, 8),
        ),
    ]


def load_clean_file(path: Path) -> pd.DataFrame:
    """Read a clean tariff CSV with every value kept as text.

    Types are converted explicitly afterwards, so malformed values surface as
    validation failures instead of being silently guessed by pandas.

    Args:
        path: Path to the clean CSV.

    Returns:
        DataFrame with all values as strings.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is empty, unparseable or not UTF-8.
    """
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Clean tariff file not found: {path}. "
            "Run scripts/process_esco_balancing_tariffs.py first."
        ) from exc
    except pd.errors.EmptyDataError as exc:
        raise ValueError(f"Clean tariff file is empty: {path}") from exc
    except pd.errors.ParserError as exc:
        raise ValueError(f"Could not parse clean tariff file {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"Clean tariff file is not valid UTF-8: {path}") from exc


def coerce_types(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Convert columns to their expected types; unparseable values become null.

    Args:
        raw_df: DataFrame as returned by load_clean_file.

    Returns:
        DataFrame with numeric columns as numbers and date as datetime.
    """
    typed_df = raw_df.copy()
    for column in NUMERIC_COLUMNS:
        typed_df[column] = pd.to_numeric(typed_df[column].str.strip(), errors="coerce")
    typed_df["date"] = pd.to_datetime(typed_df["date"].str.strip(), format="%Y-%m-%d", errors="coerce")
    typed_df["month"] = typed_df["month"].str.strip()
    return typed_df


def check_hard_failures(raw_df: pd.DataFrame, target: ValidationTarget) -> tuple[list[str], pd.DataFrame | None]:
    """Run all structural checks that make a file unusable if they fail.

    Args:
        raw_df: DataFrame as returned by load_clean_file.
        target: File definition, used for messages.

    Returns:
        Tuple of (failure messages, typed DataFrame). The DataFrame is None
        when a failure prevents further checks.
    """
    prefix = f"[{target.name}]"

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in raw_df.columns]
    if missing_columns:
        return [f"{prefix} missing required columns: {missing_columns}"], None

    typed_df = coerce_types(raw_df)
    failures: list[str] = []

    if len(typed_df) != EXPECTED_ROW_COUNT:
        failures.append(f"{prefix} expected {EXPECTED_ROW_COUNT} rows, found {len(typed_df)}")

    null_counts = typed_df[[*NUMERIC_COLUMNS, "date"]].isna().sum()
    blank_months = int((typed_df["month"] == "").sum())
    if null_counts.any() or blank_months:
        detail = {column: int(count) for column, count in null_counts.items() if count}
        if blank_months:
            detail["month"] = blank_months
        failures.append(f"{prefix} null or unparseable values: {detail}")
        return failures, None

    found_years = sorted(typed_df["year"].astype(int).unique().tolist())
    if found_years != list(EXPECTED_YEARS):
        failures.append(f"{prefix} expected years {list(EXPECTED_YEARS)}, found {found_years}")

    for year, group in typed_df.groupby("year"):
        months = sorted(group["month_number"].astype(int).tolist())
        if months != list(range(1, 13)):
            failures.append(f"{prefix} year {int(year)} does not contain exactly months 1-12: {months}")

    duplicate_dates = int(typed_df["date"].duplicated().sum())
    if duplicate_dates:
        failures.append(f"{prefix} {duplicate_dates} duplicate dates")

    non_positive = int((typed_df["tariff_tetri_per_kwh"] <= 0).sum())
    if non_positive:
        failures.append(f"{prefix} {non_positive} tariff values are zero or negative")

    conversion_error = (
        typed_df["tariff_gel_per_mwh"] - typed_df["tariff_tetri_per_kwh"] * TETRI_PER_KWH_TO_GEL_PER_MWH
    ).abs()
    bad_conversions = int((conversion_error > CONVERSION_TOLERANCE).sum())
    if bad_conversions:
        failures.append(
            f"{prefix} {bad_conversions} rows where tariff_gel_per_mwh != "
            f"tariff_tetri_per_kwh * 10 (tolerance {CONVERSION_TOLERANCE})"
        )

    date_matches = (
        (typed_df["date"].dt.year == typed_df["year"])
        & (typed_df["date"].dt.month == typed_df["month_number"])
        & (typed_df["date"].dt.day == 1)
    )
    inconsistent_dates = int((~date_matches).sum())
    if inconsistent_dates:
        failures.append(
            f"{prefix} {inconsistent_dates} rows where date does not match year/month_number "
            "or is not the first day of the month"
        )

    return failures, typed_df


def check_month_on_month(typed_df: pd.DataFrame, target: ValidationTarget) -> list[str]:
    """Flag month-on-month tariff changes larger than MONTH_ON_MONTH_THRESHOLD.

    For a series with a fixed summer tariff, the transitions into and out of
    the summer window are expected regime switches and are not flagged.

    Args:
        typed_df: Typed DataFrame that passed all hard checks.
        target: File definition.

    Returns:
        List of anomaly flag messages.
    """
    ordered = typed_df.sort_values("date").reset_index(drop=True)
    flags: list[str] = []

    for index in range(1, len(ordered)):
        previous = ordered.iloc[index - 1]
        current = ordered.iloc[index]

        if target.fixed_summer_months:
            previous_in_summer = int(previous["month_number"]) in target.fixed_summer_months
            current_in_summer = int(current["month_number"]) in target.fixed_summer_months
            if previous_in_summer != current_in_summer:
                continue

        previous_value = float(previous["tariff_tetri_per_kwh"])
        current_value = float(current["tariff_tetri_per_kwh"])
        change = (current_value - previous_value) / previous_value

        if abs(change) > MONTH_ON_MONTH_THRESHOLD:
            flags.append(
                f"[{target.name}] {current['date']:%Y-%m}: month-on-month change {change:+.1%} "
                f"({previous_value:.4f} -> {current_value:.4f} tetri/kWh)"
            )

    return flags


def check_extreme_values(typed_df: pd.DataFrame, target: ValidationTarget) -> list[str]:
    """Flag values outside Tukey fences at IQR_MULTIPLIER x the interquartile range.

    Args:
        typed_df: Typed DataFrame that passed all hard checks.
        target: File definition.

    Returns:
        List of anomaly flag messages.
    """
    values = typed_df["tariff_tetri_per_kwh"]
    first_quartile, third_quartile = values.quantile([0.25, 0.75]).tolist()
    spread = third_quartile - first_quartile
    lower_fence = first_quartile - IQR_MULTIPLIER * spread
    upper_fence = third_quartile + IQR_MULTIPLIER * spread

    outliers = typed_df[(values < lower_fence) | (values > upper_fence)].sort_values("date")
    return [
        f"[{target.name}] {row.date:%Y-%m}: extreme value {row.tariff_tetri_per_kwh:.4f} tetri/kWh "
        f"(fences {lower_fence:.4f} to {upper_fence:.4f})"
        for row in outliers.itertuples(index=False)
    ]


def check_fixed_summer_tariff(typed_df: pd.DataFrame, target: ValidationTarget) -> list[str]:
    """Flag years where the expected fixed summer tariff is not a single value.

    Args:
        typed_df: Typed DataFrame that passed all hard checks.
        target: File definition; the check is skipped if it has no summer window.

    Returns:
        List of anomaly flag messages.
    """
    if not target.fixed_summer_months:
        return []

    flags: list[str] = []
    for year, group in typed_df.groupby("year"):
        summer = group[group["month_number"].isin(target.fixed_summer_months)].sort_values("month_number")
        summer_values = summer["tariff_tetri_per_kwh"].to_numpy()
        if not np.allclose(summer_values, summer_values[0], rtol=0.0, atol=1e-9):
            flags.append(
                f"[{target.name}] {int(year)}: summer months {list(target.fixed_summer_months)} "
                f"are not a single fixed tariff: {summer_values.tolist()}"
            )
        else:
            logger.info(
                "[%s] %d: fixed summer tariff confirmed at %.4f tetri/kWh",
                target.name,
                int(year),
                summer_values[0],
            )
    return flags


def validate_target(target: ValidationTarget) -> ValidationReport:
    """Run all hard checks and, if they pass, all anomaly checks on one file.

    Args:
        target: File definition.

    Returns:
        ValidationReport with hard failures and anomaly flags.
    """
    report = ValidationReport()
    logger.info("[%s] Validating %s", target.name, target.path.relative_to(REPO_ROOT))

    try:
        raw_df = load_clean_file(target.path)
    except (FileNotFoundError, ValueError) as exc:
        report.hard_failures.append(f"[{target.name}] {exc}")
        return report

    failures, typed_df = check_hard_failures(raw_df, target)
    report.hard_failures.extend(failures)

    if report.hard_failures or typed_df is None:
        logger.info("[%s] Skipping anomaly checks because hard checks failed", target.name)
        return report

    report.anomaly_flags.extend(check_month_on_month(typed_df, target))
    report.anomaly_flags.extend(check_extreme_values(typed_df, target))
    report.anomaly_flags.extend(check_fixed_summer_tariff(typed_df, target))
    return report


def main() -> int:
    """Validate all tariff files and log a summary.

    Returns:
        Process exit code: 0 if there are no hard failures, 1 otherwise.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    total_failures = 0
    total_flags = 0

    for target in build_validation_targets():
        report = validate_target(target)

        for message in report.hard_failures:
            logger.error(message)
        for message in report.anomaly_flags:
            logger.warning(message)

        if not report.hard_failures:
            logger.info(
                "[%s] Hard checks passed | anomaly flags: %d",
                target.name,
                len(report.anomaly_flags),
            )

        total_failures += len(report.hard_failures)
        total_flags += len(report.anomaly_flags)

    logger.info("Summary | hard failures: %d | anomaly flags: %d", total_failures, total_flags)

    if total_failures:
        logger.error("Validation FAILED. Do not run the join until the hard failures are fixed.")
        return 1

    logger.info("Validation passed. Review any anomaly flags before publishing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())