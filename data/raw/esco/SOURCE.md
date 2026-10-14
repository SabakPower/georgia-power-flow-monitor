# Source: ESCO balancing electricity tariffs (raw)

These files record regulated ESCO settlement tariffs. They are NOT market prices
and must never be labelled or analysed as such.

## balancing_price_sold_wide.csv

- **Series:** Weighted average tariff of balancing electricity sold by ESCO
- **Source URL:** https://esco.ge/ka/electricity/balancing-electricity-price
- **Retrieval date:** 2026-10-13
- **Unit:** tetri/kWh (multiply by 10 for GEL/MWh)
- **Coverage in file:** 2022-01 to 2025-12 (48 monthly values)
- **Method:** Transcribed manually from the HTML table on the ESCO website
  (Georgian-language page). No file download is offered by the source.

## balancing_price_purchased_small_plants_wide.csv

- **Series:** Tariff of balancing electricity purchased by ESCO from small-capacity
  deregulated power plants
- **Source title (Georgian, as published):** მცირე სიმძლავრის დერეგულირებული
  ელექტროსადგურებიდან ესკო-ს მიერ შესყიდული საბალანსო ელექტროენერგიის ფასი, 2022-2026 წწ
- **Source URL:** https://esco.ge/ka/electricity/balancing-electricity-price-of-the-deregulated-power-plants
- **Retrieval date:** 2026-10-13
- **Unit:** tetri/kWh (multiply by 10 for GEL/MWh)
- **Coverage in file:** 2022-01 to 2025-12 (48 monthly values)
- **Method:** Transcribed manually from the HTML table on the ESCO website
  (Georgian-language page). No file download is offered by the source.

## Transcription decisions (apply to both files)

1. Georgian month names were translated to English (January to December).
2. Stray whitespace around values in the source HTML was trimmed.
3. All digits are kept exactly as published, including trailing zeros.
4. **2026 deliberately excluded.** ESCO had published January to August 2026 at
   retrieval. The analysis scope is 2022 to 2025, so 2026 was not transcribed.
   It is not missing data.

## Known source defects (preserved, not fixed)

- `balancing_price_sold_wide.csv`, July 2024: published as `15,6159665`
  (comma decimal separator). Kept exactly as published and quoted in the CSV so
  the comma is not read as a column separator. Correction happens in the
  processing step and is logged there.

## Rules

- Files in this folder are never modified after creation.
- Adding 2026 (planned for January 2027) means saving a NEW file alongside these,
  e.g. `balancing_price_sold_wide_2022_2026.csv`. Do not edit these files.