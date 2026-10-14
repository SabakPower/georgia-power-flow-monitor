"""Join the ESCO electricity balance with the ESCO balancing electricity tariffs.

Combines the monthly electricity balance (energy volumes) with the two monthly
balancing electricity tariff series into one analysis-ready file.

Coverage: the balance data covers 2021-2025, the tariff data 2022-2025. The
balance data is restricted to the 2022-2025 overlap BEFORE joining, and every
output row is checked so that no month is silently lost or duplicated.

All values are carried through as text, exactly as they appear in the processed
inputs; only the date keys are parsed. The join therefore never reformats or
rounds any balance or tariff value.

These are regulated ESCO settlement tariffs. They are NOT market prices.

Usage:
    python scripts/join_esco_balance_and_balancing_tariffs.py
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

REPO_ROOT: Path = Path(__file__).resolve().parents[1]
PROCESSED_DIR: Path = REPO_ROOT / "data" / "processed" / "esco"

BALANCE_PATH: Path = PROCESSED_DIR / "electricity_balance_monthly_clean.csv"
OUTPUT_PATH: Path = PROCESSED_DIR / "electricity_balance_with_balancing_tariffs_monthly.csv"

EXPECTED_YEARS: tuple[int, ...] = (2022, 2023, 2024, 2025)
EXPECTED_JOINED_ROWS: int = len(EXPECTED_YEARS) * 12

# Balance data starts in 2021; tariff coverage starts in 2022. Exactly the 12
# months of 2021 are expected to fall outside the overlap. Any other result
# means one of the inputs has changed and the join must be reviewed.
EXPECTED_EXCLUDED_YEARS: tuple[int, ...] = (2021,)
EXPECTED_EXCLUDED_ROWS: int = 12

MONTH_KEY: str = "_month_key"

logger: logging.Logger = logging.getLogger("join_esco_balance_and_balancing_tariffs")


@dataclass(frozen=True)
class TariffInput:
    """Definition of one clean tariff file to join onto the balance data.

    Attributes:
        name: Short identifier used in log messages.
        path: Path to the clean tariff CSV.
        output_column: Name of the column added to the joined output.
    """

    name: str
    path: Path
    output_column: str


def build_tariff_inputs() -> list[TariffInput]:
    """Return the two tariff files to join.

    Returns:
        List of TariffInput definitions, in output column order.
    """
    return [
        TariffInput(
            name="sold",
            path=PROCESSED_DIR / "balancing_tariff_sold_monthly_clean.csv",
            output_column="balancing_tariff_sold_gel_per_mwh",
        ),
        TariffInput(
            name="purchased_small_plants",
            path=PROCESSED_DIR / "balancing_tariff_purchased_small_plants_monthly_clean.csv",
            output_column="balancing_tariff_purchased_small_plants_gel_per_mwh",
        ),
    ]


def read_csv_as_text(path: Path, label: str) -> pd.DataFrame:
    """Read a CSV with every value kept as text.

    Args:
        path: Path to the CSV.
        label: Description used in error messages.

    Returns:
        DataFrame with all values as strings.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is empty, unparseable or not UTF-8.
    """
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"{label} file not found: {path}") from exc
    except pd.errors.EmptyDataError as exc:
        raise ValueError(f"{label} file is empty: {path}") from exc
    except pd.errors.ParserError as exc:
        raise ValueError(f"Could not parse {label} file {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} file is not valid UTF-8: {path}") from exc


def build_month_key(df: pd.DataFrame, label: str) -> pd.Series:
    """Parse the date column into a first-of-month timestamp used as the join key.

    If the file also has year and month_number columns, they must agree with
    the parsed date.

    Args:
        df: DataFrame with a text date column.
        label: Description used in log and error messages.

    Returns:
        Series of first-of-month timestamps aligned with df.

    Raises:
        ValueError: If the date column is missing, a date cannot be parsed, or
            dates disagree with year/month_number.
    """
    if "date" not in df.columns:
        raise ValueError(f"{label}: required column 'date' is missing")

    parsed = pd.to_datetime(df["date"].str.strip(), errors="coerce")
    unparseable = df.loc[parsed.isna(), "date"].tolist()
    if unparseable:
        raise ValueError(f"{label}: could not parse dates: {unparseable[:5]}")

    month_key = parsed.dt.to_period("M").dt.to_timestamp()
    normalised = int((parsed != month_key).sum())
    if normalised:
        logger.info("%s: %d dates normalised to the first day of their month", label, normalised)

    if {"year", "month_number"}.issubset(df.columns):
        years = pd.to_numeric(df["year"].str.strip(), errors="coerce")
        months = pd.to_numeric(df["month_number"].str.strip(), errors="coerce")
        mismatches = int(((month_key.dt.year != years) | (month_key.dt.month != months)).sum())
        if mismatches:
            raise ValueError(f"{label}: {mismatches} rows where date disagrees with year/month_number")

    return month_key


def load_balance() -> pd.DataFrame:
    """Load the processed electricity balance with a month join key.

    Returns:
        Balance DataFrame (all original columns as text) plus MONTH_KEY.

    Raises:
        ValueError: If dates are invalid or duplicated.
    """
    balance_df = read_csv_as_text(BALANCE_PATH, "Electricity balance")
    balance_df[MONTH_KEY] = build_month_key(balance_df, "Electricity balance")

    duplicates = int(balance_df[MONTH_KEY].duplicated().sum())
    if duplicates:
        raise ValueError(f"Electricity balance: {duplicates} duplicate months")

    logger.info(
        "Electricity balance loaded | rows: %d | coverage: %s to %s",
        len(balance_df),
        balance_df[MONTH_KEY].min().strftime("%Y-%m"),
        balance_df[MONTH_KEY].max().strftime("%Y-%m"),
    )
    return balance_df


def restrict_to_overlap(balance_df: pd.DataFrame) -> pd.DataFrame:
    """Keep only balance months inside the tariff coverage (2022-2025).

    Args:
        balance_df: Balance DataFrame with MONTH_KEY.

    Returns:
        Balance DataFrame restricted to EXPECTED_YEARS.

    Raises:
        ValueError: If the excluded rows are not exactly the expected 12
            months of 2021, or the remaining rows are not 48.
    """
    in_overlap = balance_df[MONTH_KEY].dt.year.isin(EXPECTED_YEARS)
    excluded = balance_df.loc[~in_overlap]
    excluded_years = tuple(sorted(excluded[MONTH_KEY].dt.year.unique().tolist()))

    if len(excluded) != EXPECTED_EXCLUDED_ROWS or excluded_years != EXPECTED_EXCLUDED_YEARS:
        raise ValueError(
            f"Expected to exclude {EXPECTED_EXCLUDED_ROWS} rows from years "
            f"{list(EXPECTED_EXCLUDED_YEARS)}, but would exclude {len(excluded)} rows "
            f"from years {list(excluded_years)}. An input has changed; review before joining."
        )

    logger.info(
        "Excluded %d balance rows from %s: tariff coverage starts in %d",
        len(excluded),
        list(excluded_years),
        EXPECTED_YEARS[0],
    )

    restricted = balance_df.loc[in_overlap].copy()
    if len(restricted) != EXPECTED_JOINED_ROWS:
        raise ValueError(
            f"Electricity balance has {len(restricted)} rows in {list(EXPECTED_YEARS)}, "
            f"expected {EXPECTED_JOINED_ROWS}"
        )
    return restricted


def load_tariff(tariff_input: TariffInput) -> pd.DataFrame:
    """Load one clean tariff file, keeping only the join key and GEL/MWh column.

    Args:
        tariff_input: Tariff file definition.

    Returns:
        DataFrame with MONTH_KEY and the tariff column renamed to
        tariff_input.output_column.

    Raises:
        ValueError: If required columns are missing, values are blank, or
            months are duplicated.
    """
    label = f"Tariff [{tariff_input.name}]"
    tariff_df = read_csv_as_text(tariff_input.path, label)

    if "tariff_gel_per_mwh" not in tariff_df.columns:
        raise ValueError(f"{label}: required column 'tariff_gel_per_mwh' is missing")

    blank_values = int((tariff_df["tariff_gel_per_mwh"].str.strip() == "").sum())
    if blank_values:
        raise ValueError(f"{label}: {blank_values} blank tariff values")

    tariff_df[MONTH_KEY] = build_month_key(tariff_df, label)

    duplicates = int(tariff_df[MONTH_KEY].duplicated().sum())
    if duplicates:
        raise ValueError(f"{label}: {duplicates} duplicate months")

    return tariff_df[[MONTH_KEY, "tariff_gel_per_mwh"]].rename(
        columns={"tariff_gel_per_mwh": tariff_input.output_column}
    )


def join_frames(balance_df: pd.DataFrame, tariff_frames: list[tuple[TariffInput, pd.DataFrame]]) -> pd.DataFrame:
    """Inner-join each tariff onto the balance data on the month key.

    Args:
        balance_df: Balance DataFrame restricted to the overlap.
        tariff_frames: (definition, DataFrame) pairs from load_tariff.

    Returns:
        Joined DataFrame with the balance columns followed by one column per
        tariff.

    Raises:
        ValueError: If a tariff column name already exists in the balance data.
        pandas.errors.MergeError: If a join is not one-to-one.
    """
    joined = balance_df
    for tariff_input, tariff_df in tariff_frames:
        if tariff_input.output_column in joined.columns:
            raise ValueError(f"Column '{tariff_input.output_column}' already exists in the balance data")
        joined = joined.merge(tariff_df, on=MONTH_KEY, how="inner", validate="one_to_one")
        logger.info("Joined tariff [%s] | rows after join: %d", tariff_input.name, len(joined))
    return joined.sort_values(MONTH_KEY).reset_index(drop=True)


def validate_joined(joined_df: pd.DataFrame, tariff_inputs: list[TariffInput]) -> None:
    """Check the joined output before it is written.

    Args:
        joined_df: DataFrame returned by join_frames.
        tariff_inputs: Tariff definitions, used to locate the added columns.

    Raises:
        ValueError: Listing every failed check, if any check fails.
    """
    failures: list[str] = []

    if len(joined_df) != EXPECTED_JOINED_ROWS:
        failures.append(f"expected {EXPECTED_JOINED_ROWS} rows, found {len(joined_df)}")

    years = sorted(joined_df[MONTH_KEY].dt.year.unique().tolist())
    if years != list(EXPECTED_YEARS):
        failures.append(f"expected years {list(EXPECTED_YEARS)}, found {years}")

    for year, group in joined_df.groupby(joined_df[MONTH_KEY].dt.year):
        months = sorted(group[MONTH_KEY].dt.month.tolist())
        if months != list(range(1, 13)):
            failures.append(f"year {year} does not contain exactly months 1-12: {months}")

    for tariff_input in tariff_inputs:
        column = tariff_input.output_column
        values = pd.to_numeric(joined_df[column].str.strip(), errors="coerce")
        if values.isna().any():
            failures.append(f"{int(values.isna().sum())} null or non-numeric values in {column}")
        elif (values <= 0).any():
            failures.append(f"{int((values <= 0).sum())} zero or negative values in {column}")

    if failures:
        raise ValueError("Joined output failed validation: " + "; ".join(failures))


def write_joined(joined_df: pd.DataFrame) -> None:
    """Write the joined output without the internal join key.

    Args:
        joined_df: Validated joined DataFrame.

    Raises:
        OSError: If the file cannot be written.
    """
    output_df = joined_df.drop(columns=[MONTH_KEY])
    try:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        output_df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")
    except OSError as exc:
        raise OSError(f"Could not write joined file {OUTPUT_PATH}: {exc}") from exc


def main() -> int:
    """Load, restrict, join, validate and write the joined dataset.

    Returns:
        Process exit code: 0 on success, 1 on any failure.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    tariff_inputs = build_tariff_inputs()

    try:
        balance_df = restrict_to_overlap(load_balance())
        tariff_frames = [(tariff_input, load_tariff(tariff_input)) for tariff_input in tariff_inputs]
        joined_df = join_frames(balance_df, tariff_frames)
        validate_joined(joined_df, tariff_inputs)
        write_joined(joined_df)
    except (FileNotFoundError, ValueError, OSError, pd.errors.MergeError) as exc:
        logger.error("Join failed: %s", exc)
        return 1

    for tariff_input in tariff_inputs:
        logger.info("No nulls in %s", tariff_input.output_column)

    logger.info(
        "Wrote %s | rows: %d | coverage: %s to %s",
        OUTPUT_PATH.relative_to(REPO_ROOT),
        len(joined_df),
        joined_df[MONTH_KEY].min().strftime("%Y-%m"),
        joined_df[MONTH_KEY].max().strftime("%Y-%m"),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())