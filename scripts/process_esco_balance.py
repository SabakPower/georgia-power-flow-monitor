import pandas as pd
from pathlib import Path

INPUT_FILE = Path("data/raw/esco/electricity_balance_monthly.csv")
OUTPUT_FILE = Path("data/processed/esco/electricity_balance_monthly_clean.csv")


def main():
    df = pd.read_csv(INPUT_FILE)

    # Clean small negative zero artefacts caused by rounding
    numeric_cols = df.select_dtypes(include="number").columns
    df[numeric_cols] = df[numeric_cols].round(3)
    df[numeric_cols] = df[numeric_cols].mask(df[numeric_cols].abs() < 0.0005, 0)

    # Create date column for dashboard charts
    df["date"] = pd.to_datetime(
        df["year"].astype(str) + "-" + df["month_number"].astype(str) + "-01"
    )

    # Core indicators
    df["net_imports_mln_kwh"] = df["import_mln_kwh"] - df["export_mln_kwh"]

    df["hydro_share_pct"] = (
        df["hydro_mln_kwh"] / df["generation_mln_kwh"] * 100
    ).round(2)

    df["thermal_share_pct"] = (
        df["thermal_mln_kwh"] / df["generation_mln_kwh"] * 100
    ).round(2)

    df["wind_share_pct"] = (
        df["wind_mln_kwh"] / df["generation_mln_kwh"] * 100
    ).round(2)

    df["other_generation_share_pct"] = (
        df["other_generation_mln_kwh"] / df["generation_mln_kwh"] * 100
    ).round(2)

    df["import_dependency_pct"] = (
        df["import_mln_kwh"] / df["total_demand_including_losses_mln_kwh"] * 100
    ).round(2)

    df["export_share_of_generation_pct"] = (
        df["export_mln_kwh"] / df["generation_mln_kwh"] * 100
    ).round(2)

    df["transportation_expenses_share_pct"] = (
        df["transportation_expenses_mln_kwh"]
        / df["total_demand_including_losses_mln_kwh"]
        * 100
    ).round(2)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False)

    print("Processed ESCO dataset created.")
    print(f"Rows: {len(df)}")
    print(f"Columns: {len(df.columns)}")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()