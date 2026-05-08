import pandas as pd

INPUT_FILE = "data/raw/esco/electricity_balance_monthly.csv"
TOLERANCE = 0.05  # allows small rounding differences in ESCO data


def check_balance(df, check_name, calculated, reported):
    difference = (calculated - reported).abs()
    failed = df[difference > TOLERANCE].copy()

    if failed.empty:
        print(f"PASS: {check_name}")
    else:
        print(f"\nFAIL: {check_name}")
        failed["difference"] = difference[difference > TOLERANCE]
        print(failed[["year", "month", "difference"]])


def main():
    df = pd.read_csv(INPUT_FILE)

    print("ESCO Electricity Balance Validation")
    print("-----------------------------------")
    print(f"Rows: {len(df)}")
    print(f"Columns: {len(df.columns)}")
    print()

    check_balance(
        df,
        "Generation = Thermal + Wind + Hydro + Other Generation",
        df["thermal_mln_kwh"]
        + df["wind_mln_kwh"]
        + df["hydro_mln_kwh"]
        + df["other_generation_mln_kwh"],
        df["generation_mln_kwh"],
    )

    check_balance(
        df,
        "Hydro = Regulatory + Seasonal + Small Hydro",
        df["hydro_regulatory_mln_kwh"]
        + df["hydro_seasonal_mln_kwh"]
        + df["hydro_small_mln_kwh"],
        df["hydro_mln_kwh"],
    )

    check_balance(
        df,
        "Total Resource = Generation + Import + Transit",
        df["generation_mln_kwh"] + df["import_mln_kwh"] + df["transit_mln_kwh"],
        df["total_resource_mln_kwh"],
    )

    check_balance(
        df,
        "Delivery to Network = Total Resource - Plant Losses/Self-consumption",
        df["total_resource_mln_kwh"] - df["plant_losses_self_consumption_mln_kwh"],
        df["delivery_to_network_mln_kwh"],
    )

    check_balance(
        df,
        "Supplied to Consumers = Distribution Companies + Direct Customers + Self-consumption of Stopped Plants",
        df["distribution_companies_mln_kwh"]
        + df["direct_customers_mln_kwh"]
        + df["self_consumption_stopped_plants_mln_kwh"],
        df["supplied_to_consumers_mln_kwh"],
    )

    check_balance(
        df,
        "Supplied Consumers and Export = Supplied Consumers + Export + Transit",
        df["supplied_to_consumers_mln_kwh"]
        + df["export_mln_kwh"]
        + df["transit_mln_kwh"],
        df["supplied_consumers_and_export_mln_kwh"],
    )

    check_balance(
        df,
        "Total Demand Including Losses = Supplied Consumers and Export + Transportation Expenses",
        df["supplied_consumers_and_export_mln_kwh"]
        + df["transportation_expenses_mln_kwh"],
        df["total_demand_including_losses_mln_kwh"],
    )

    print()
    print("Validation complete.")


if __name__ == "__main__":
    main()