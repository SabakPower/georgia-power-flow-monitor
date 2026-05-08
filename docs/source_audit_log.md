## ESCO — Electricity Balance

Date checked:
2026-05-08

Source:
ESCO — Electricity Balance 2025

Source URL:
[Paste the exact ESCO page URL you used]

Data category:
Electricity balance

Dataset created:
data/raw/esco/electricity_balance_monthly.csv

Collection method:
Manual extraction from ESCO electricity balance table.

Format observed:
Web table / PDF-style balance page.

Frequency:
Annual page with monthly values.

Granularity:
Monthly.

Coverage added:
2025, January to December.

Rows:
12

Columns:
28

Key fields:
- generation_mln_kwh
- thermal_mln_kwh
- wind_mln_kwh
- hydro_mln_kwh
- other_generation_mln_kwh
- import_mln_kwh
- export_mln_kwh
- transit_mln_kwh
- total_resource_mln_kwh
- total_demand_including_losses_mln_kwh

Validation:
Passed structural and mathematical validation using scripts/validate_esco_balance.py.

Important modelling note:
The residual between total generation and visible generation categories was added as other_generation_mln_kwh. It should not be labelled as solar or any other technology until verified from an official source.

Limitations:
- Manual extraction may introduce typing errors.
- Source structure must be checked for other years.
- Need to verify whether values are final or preliminary.
- Need to confirm exact unit convention from ESCO source.

Decision:
Selected as the first dataset candidate for the dashboard.