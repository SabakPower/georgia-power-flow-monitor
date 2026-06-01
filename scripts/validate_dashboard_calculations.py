from pathlib import Path
import logging

import pandas as pd


DATA_FILE = Path("data/processed/esco/electricity_balance_monthly_clean.csv")
TOLERANCE = 0.05

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def calculate_share_pct(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Calculate percentage shares safely, avoiding division by zero."""
    safe_denominator = denominator.where(denominator != 0)
    return numerator.div(safe_denominator).mul(100).round(2)


def check_required_columns(df: pd.DataFrame, required_columns: list[str]) -> None:
    """Validate that all required input columns exist."""
    missing_columns = [column for column in required_columns if column not in df.columns]

    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")


def check_numeric_match(
    df: pd.DataFrame,
    check_name: str,
    calculated: pd.Series,
    expected: pd.Series,
    tolerance: float = TOLERANCE,
) -> None:
    """Compare calculated and expected numeric series."""
    difference = (calculated - expected).abs()
    failed_rows = df[difference > tolerance].copy()

    if failed_rows.empty:
        logger.info("PASS: %s", check_name)
        return

    failed_rows["difference"] = difference[difference > tolerance]
    logger.error("FAIL: %s", check_name)
    logger.error("\n%s", failed_rows[["year", "month", "difference"]])

    raise ValueError(f"Validation failed: {check_name}")


def validate_date_column(df: pd.DataFrame) -> None:
    """Validate that the date column matches year and month_number."""
    expected_dates = pd.to_datetime(
        df["year"].astype(str) + "-" + df["month_number"].astype(str) + "-01"
    )
    reported_dates = pd.to_datetime(df["date"])

    if expected_dates.equals(reported_dates):
        logger.info("PASS: Date column matches year and month_number")
        return

    raise ValueError("Validation failed: date column does not match year/month_number")


def validate_dashboard_calculations(df: pd.DataFrame) -> None:
    """Validate calculations used in the Streamlit dashboard."""
    total_generation = (
        df["hydro_mln_kwh"]
        + df["thermal_mln_kwh"]
        + df["wind_mln_kwh"]
        + df["other_generation_mln_kwh"]
    )

    non_hydro_generation = (
        df["thermal_mln_kwh"]
        + df["wind_mln_kwh"]
        + df["other_generation_mln_kwh"]
    )

    calculated_net_imports = df["import_mln_kwh"] - df["export_mln_kwh"]

    check_numeric_match(
        df=df,
        check_name="Generation mix total = Hydro + Thermal + Wind + Other",
        calculated=total_generation,
        expected=df["generation_mln_kwh"],
    )

    check_numeric_match(
        df=df,
        check_name="Net imports = Imports - Exports",
        calculated=calculated_net_imports,
        expected=df["net_imports_mln_kwh"],
    )

    hydro_share_pct = calculate_share_pct(df["hydro_mln_kwh"], total_generation)
    non_hydro_share_pct = calculate_share_pct(non_hydro_generation, total_generation)

    check_numeric_match(
        df=df,
        check_name="Hydro share + Non-hydro share = 100%",
        calculated=hydro_share_pct + non_hydro_share_pct,
        expected=pd.Series(100.0, index=df.index),
    )

    thermal_non_hydro_share_pct = calculate_share_pct(
        df["thermal_mln_kwh"], non_hydro_generation
    )
    wind_non_hydro_share_pct = calculate_share_pct(
        df["wind_mln_kwh"], non_hydro_generation
    )
    other_non_hydro_share_pct = calculate_share_pct(
        df["other_generation_mln_kwh"], non_hydro_generation
    )

    non_hydro_share_total = (
        thermal_non_hydro_share_pct
        + wind_non_hydro_share_pct
        + other_non_hydro_share_pct
    )

    valid_non_hydro_rows = non_hydro_generation != 0

    check_numeric_match(
        df=df[valid_non_hydro_rows],
        check_name="Thermal + Wind + Other shares within non-hydro = 100%",
        calculated=non_hydro_share_total[valid_non_hydro_rows],
        expected=pd.Series(100.0, index=df[valid_non_hydro_rows].index),
    )

    net_import_position_pct = calculate_share_pct(
        calculated_net_imports,
        df["total_consumption_mln_kwh"],
    )

    logger.info("PASS: Net import position calculated safely")
    logger.info(
        "Net importer months: %s",
        int((net_import_position_pct > 0).sum()),
    )
    logger.info(
        "Net exporter months: %s",
        int((net_import_position_pct < 0).sum()),
    )

    generation_balance = df["generation_mln_kwh"] - df["total_consumption_mln_kwh"]

    logger.info("PASS: Generation balance calculated safely")
    logger.info(
        "Generation surplus months: %s",
        int((generation_balance > 0).sum()),
    )
    logger.info(
        "Generation deficit months: %s",
        int((generation_balance < 0).sum()),
    )


def main() -> None:
    """Run dashboard calculation validation checks."""
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Processed dataset not found: {DATA_FILE}")

    df = pd.read_csv(DATA_FILE)

    required_columns = [
        "year",
        "month",
        "month_number",
        "date",
        "generation_mln_kwh",
        "hydro_mln_kwh",
        "thermal_mln_kwh",
        "wind_mln_kwh",
        "other_generation_mln_kwh",
        "import_mln_kwh",
        "export_mln_kwh",
        "net_imports_mln_kwh",
        "total_consumption_mln_kwh",
    ]

    check_required_columns(df, required_columns)

    logger.info("Dashboard Calculation Validation")
    logger.info("--------------------------------")
    logger.info("Rows: %s", len(df))
    logger.info("Columns: %s", len(df.columns))

    validate_date_column(df)
    validate_dashboard_calculations(df)

    logger.info("")
    logger.info("Dashboard calculation validation complete.")


if __name__ == "__main__":
    main()