# Georgia Power Flow Monitor

Georgia Power Flow Monitor is an open-source energy data project focused on Georgia’s electricity system.

The project collects, cleans, analyses, and visualises public electricity data from Georgian energy institutions, starting with ESCO electricity balance data and expanding toward broader power system, market, and regulatory datasets.

The long-term goal of the project is to build a transparent public reference for Georgia’s electricity generation, consumption, imports, exports, system balance, and market development.

## Project Objectives

* Track electricity generation, consumption, imports, exports, and net import position
* Clean and structure public electricity datasets from Georgian institutions
* Build a reproducible data pipeline for electricity balance analysis
* Develop a dashboard for system-level monitoring
* Create a public data source catalogue for Georgia’s electricity sector
* Document data quality checks, assumptions, and source limitations
* Share progress through GitHub and LinkedIn as a public portfolio project

## Current Scope

The current version focuses on ESCO monthly electricity balance data.

Current dashboard coverage includes:

* Total generation and total consumption
* Imports, exports, and net imports
* Domestic generation coverage
* Monthly generation versus consumption
* Domestic generation gap
* Generation by source: hydro, thermal, wind, and other generation
* Hydro dependence of domestic generation
* Non-hydro generation breakdown
* Net import position as a percentage of consumption
* Key system insights for the selected year
* Data status and processed dataset preview

## Current Data Coverage

The project currently uses monthly ESCO electricity balance data.

Planned working coverage:

* 2021–2025 ESCO monthly electricity balance data
* Selected-year dashboard analysis
* Multi-year system context for longer-term comparison

## Dashboard

The Streamlit dashboard is designed to answer core electricity system questions:

* How much electricity did Georgia generate and consume?
* Did domestic generation cover domestic consumption?
* Which generation sources dominated the system?
* How dependent was the system on hydro generation?
* When did Georgia rely most on imports?
* When did Georgia become a net exporter?
* How did the monthly generation-consumption gap change over time?

## Data Sources

### Current Source

* **ESCO** — monthly electricity balance data, including generation, consumption, imports, exports, and system balance indicators.

### Planned Sources

* **GSE** - physical power system data, generation, consumption, transmission, and cross-border flows
* **GENEX** - day-ahead and intraday electricity market data
* **GNERC** - regulatory reports, market rules, tariffs, and sector publications
* **Secondary sources** - market reports, analytical publications, and institutional documents

## Methodology

The project follows a structured data workflow:

1. Collect public electricity data from official sources
2. Store raw data separately from processed data
3. Clean and standardise column names, units, dates, and categories
4. Validate electricity balance calculations
5. Build derived indicators such as:

   * net imports
   * domestic generation coverage
   * net import position
   * hydro share
   * non-hydro generation breakdown
6. Visualise results in a Streamlit dashboard
7. Document assumptions, source issues, and validation checks

## Key Indicators

| Indicator                    | Description                                                           |
| ---------------------------- | --------------------------------------------------------------------- |
| Total Generation             | Domestic electricity generation in GWh                                |
| Total Consumption            | Domestic electricity consumption in GWh                               |
| Net Imports                  | Imports minus exports                                                 |
| Domestic Generation Coverage | Domestic generation divided by consumption                            |
| Net Import Position          | Net imports divided by consumption                                    |
| Hydro Dependence             | Hydro generation as a share of total domestic generation              |
| Non-Hydro Breakdown          | Thermal, wind, and other generation as shares of non-hydro generation |

## Technology Stack

* Python
* pandas
* Plotly
* Streamlit
* Git and GitHub
* CSV-based data processing
* Public electricity data sources

## Current Phase

**Phase 1 — ESCO electricity balance dashboard**

Completed or in progress:

* Project repository setup
* Initial data structure
* ESCO monthly electricity balance dataset
* Data cleaning workflow
* Dashboard prototype
* System overview metrics
* Generation and consumption analysis
* Import/export balance analysis
* Hydro dependence analysis
* Key system insights
* Data validation workflow

## Roadmap

### Phase 1 — ESCO Electricity Balance

* Complete 5-year ESCO electricity balance dataset
* Improve dashboard structure and visual consistency
* Add annual comparison charts
* Strengthen data validation and documentation

### Phase 2 — GSE Power System Data

* Add physical grid and power system data
* Compare ESCO commercial balance data with GSE operational data
* Track generation, consumption, and cross-border flows from a physical system perspective

### Phase 3 — GENEX Market Data

* Add day-ahead and intraday market data
* Track electricity market prices and traded volumes
* Analyse the relationship between market prices, imports, exports, and generation mix

### Phase 4 — Regulatory and Market Context

* Add GNERC reports, tariff data, and market rules
* Document major electricity market reforms
* Build a structured source catalogue for Georgian electricity sector data

### Phase 5 — Advanced Analysis

* Multi-year trend analysis
* Import dependency and self-sufficiency indicators
* Hydro seasonality analysis
* Market integration indicators
* Potential scenario and modelling extensions

## Status

The project is under active development.

The current focus is building a clean and reliable ESCO-based electricity balance dashboard before expanding into GSE, GENEX, and GNERC datasets.
