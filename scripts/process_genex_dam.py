"""Process a GENEX day-ahead market export into clean daily and monthly CSVs.

Input : MarketResultData-<date>__GENEX_.xlsx  (hourly rows: Time Point, Sum Of Volume,
        Sum Of Price GEL / USD / EUR). Any AutoFilter in the workbook is display-only;
        pandas reads hidden rows too, so the zero-volume hours are present.
Output: genex_dam_daily_clean.csv    one row per traded day
        genex_dam_monthly_clean.csv  one row per month from the first trade to the last
                                     complete month, zero months included

Assumptions (unconfirmed against the GENEX sheet): volume is MWh per hour, price is
GEL per MWh. EUR and USD columns are not used: they are 0 on 3 traded days
(2024-11-03, 2024-11-04, 2025-07-15) while GEL is positive.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

EXPECTED_COLUMNS = ["Time Point", "Sum Of Volume", "Sum Of Price GEL"]
# GENEX annual report 2025 (public): total traded and weighted average price
REFERENCE_2025 = {"volume_mwh": 129753.8, "price_gel_per_mwh": 131.4}


def load_export(path: Path) -> pd.DataFrame:
    """Read the workbook and return hourly rows with parsed timestamps."""
    try:
        raw = pd.read_excel(path, engine="openpyxl")
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Cannot read {path}: {exc}") from exc
    missing = [c for c in EXPECTED_COLUMNS if c not in raw.columns]
    if missing:
        raise RuntimeError(f"Missing columns in export: {missing}")
    df = pd.DataFrame({
        "ts": pd.to_datetime(raw["Time Point"].astype(str).str.replace(" : ", " ", regex=False),
                             format="%d-%m-%Y %H:%M"),
        "volume_mwh": pd.to_numeric(raw["Sum Of Volume"], errors="raise"),
        "price_gel": pd.to_numeric(raw["Sum Of Price GEL"], errors="raise"),
    })
    if df.ts.duplicated().any():
        raise RuntimeError("Duplicate timestamps in export")
    full = pd.date_range(df.ts.min(), df.ts.max(), freq="h")
    if len(full) != len(df):
        raise RuntimeError(f"Hourly grid has {len(full) - len(df)} missing hours")
    if (df.volume_mwh < 0).any():
        raise RuntimeError("Negative volumes in export")
    if ((df.volume_mwh > 0) & (df.price_gel <= 0)).any():
        raise RuntimeError("Hours with volume but non-positive GEL price")
    return df.sort_values("ts").reset_index(drop=True)


def build_daily(df: pd.DataFrame) -> pd.DataFrame:
    """One row per traded day: hours, volume and volume-weighted GEL price."""
    t = df[df.volume_mwh > 0].copy()
    t["date"] = t.ts.dt.normalize()
    t["pv"] = t.price_gel * t.volume_mwh
    g = t.groupby("date").agg(hours_traded=("volume_mwh", "size"), volume_mwh=("volume_mwh", "sum"),
                              pv=("pv", "sum"), price_gel_min=("price_gel", "min"),
                              price_gel_max=("price_gel", "max")).reset_index()
    g["price_gel_per_mwh"] = g.pv / g.volume_mwh
    g["data_quality_flag"] = g.hours_traded.map(lambda h: "ok" if h == 24 else "fewer_than_24_hours")
    out = g[["date", "hours_traded", "volume_mwh", "price_gel_per_mwh", "price_gel_min",
             "price_gel_max", "data_quality_flag"]]
    out = out.round({"volume_mwh": 1, "price_gel_per_mwh": 2, "price_gel_min": 2, "price_gel_max": 2})
    return out


def build_monthly(daily: pd.DataFrame, last_complete_month: str, supply_csv: Path | None) -> pd.DataFrame:
    """Monthly table from first trade month to last_complete_month; zero months kept."""
    d = daily.copy()
    d["period"] = d.date.dt.to_period("M")
    d["pv"] = d.price_gel_per_mwh * d.volume_mwh
    m = d.groupby("period").agg(days_traded=("date", "size"), hours_traded=("hours_traded", "sum"),
                                volume_mwh=("volume_mwh", "sum"), pv=("pv", "sum"))
    idx = pd.period_range(m.index.min(), pd.Period(last_complete_month, "M"), freq="M")
    if m.index.max() > idx.max():
        raise RuntimeError("Trades exist after last_complete_month; move the cut-off")
    m = m.reindex(idx)
    m[["days_traded", "hours_traded", "volume_mwh", "pv"]] = m[["days_traded", "hours_traded",
                                                                  "volume_mwh", "pv"]].fillna(0)
    m["price_gel_per_mwh"] = (m.pv / m.volume_mwh).where(m.volume_mwh > 0)
    m["volume_gwh"] = m.volume_mwh / 1000
    m["esco_supply_gwh"] = float("nan")
    if supply_csv is not None:
        try:
            s = pd.read_csv(supply_csv)
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Cannot read {supply_csv}: {exc}") from exc
        tot = s.groupby(["year", "month"]).supply_gwh.sum()
        m["esco_supply_gwh"] = [tot.get((p.year, p.month), float("nan")) for p in m.index]
    m["exchange_share_of_supply_pct"] = 100 * m.volume_gwh / m.esco_supply_gwh
    m["data_quality_flag"] = "ok"
    m.loc[m.volume_mwh == 0, "data_quality_flag"] = "no_cleared_volume"
    m.loc[m.esco_supply_gwh.isna(), "data_quality_flag"] = m.loc[m.esco_supply_gwh.isna(), "data_quality_flag"] \
        .map(lambda f: f if f != "ok" else "esco_supply_not_available")
    m = m.reset_index().rename(columns={"index": "period"})
    m["year"], m["month"] = m.period.dt.year, m.period.dt.month
    m["period"] = m.period.dt.to_timestamp()
    cols = ["period", "year", "month", "days_traded", "hours_traded", "volume_mwh", "volume_gwh",
            "price_gel_per_mwh", "esco_supply_gwh", "exchange_share_of_supply_pct", "data_quality_flag"]
    return m[cols].round({"volume_mwh": 1, "volume_gwh": 3, "price_gel_per_mwh": 2,
                          "esco_supply_gwh": 1, "exchange_share_of_supply_pct": 3})


def main(argv: list[str] | None = None) -> int:
    """Run the pipeline and write the two CSVs."""
    ap = argparse.ArgumentParser(description="Process a GENEX day-ahead export.")
    ap.add_argument("--xlsx", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--last-complete-month", required=True, help="e.g. 2026-09; later rows may be padding")
    ap.add_argument("--supply-csv", type=Path, default=None, help="ESCO supply CSV for the share of supply")
    args = ap.parse_args(argv)
    try:
        df = load_export(args.xlsx)
        cut = pd.Period(args.last_complete_month, "M").end_time
        daily = build_daily(df[df.ts <= cut])
        monthly = build_monthly(daily, args.last_complete_month, args.supply_csv)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    try:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        daily.to_csv(args.out_dir / "genex_dam_daily_clean.csv", index=False)
        monthly.to_csv(args.out_dir / "genex_dam_monthly_clean.csv", index=False)
    except OSError as exc:
        print(f"ERROR writing outputs: {exc}", file=sys.stderr)
        return 1
    y25 = daily[daily.date.dt.year == 2025]
    vol25 = y25.volume_mwh.sum()
    px25 = (y25.price_gel_per_mwh * y25.volume_mwh).sum() / vol25
    print(f"rows read {len(df)}; traded days {len(daily)}; months {len(monthly)} "
          f"({int((monthly.volume_mwh == 0).sum())} with no cleared volume)")
    print(f"2025 check vs GENEX report: volume {vol25:,.1f} MWh (report {REFERENCE_2025['volume_mwh']:,.1f}); "
          f"weighted price {px25:.2f} (report {REFERENCE_2025['price_gel_per_mwh']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
