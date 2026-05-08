# Source Notes

This document tracks the public data sources planned for the Georgia Power Flow Monitor project.

The purpose is to document:
- what each source provides
- how useful it is for the project
- what format the data is available in
- whether the data can be downloaded manually or later automated
- any limitations, uncertainty or cleaning issues

## Source Priority Logic

Primary sources are preferred over secondary sources.

Priority levels:
- High: likely to provide core dashboard data
- Medium: useful for market, regulatory or contextual analysis
- Low: useful mainly for interpretation, background or validation

## ESCO

Institution:
Electricity System Commercial Operator of Georgia.

Expected useful datasets:
- Electricity balance
- Generation and consumption information
- Import and export data
- Settlement indicators
- Annual reports
- Market-related electricity data

Expected use in the project:
ESCO is likely to be one of the main sources for Georgia's electricity balance.

Potential dashboard modules:
- Generation
- Consumption
- Imports
- Exports
- System balance
- Market settlement indicators

Initial assessment:
High-priority source. ESCO should be reviewed first because it is likely to contain the most relevant system-level balance data.

Open questions:
- Are datasets available as Excel/CSV or only PDF?
- How frequently are electricity balance files updated?
- Are monthly values available or only annual summaries?
- Is historical data consistently formatted?

## GSE

Institution:
Georgian State Electrosystem.

Expected useful datasets:
- Power system data
- Generation data
- Consumption data
- Transmission and grid information
- Installed capacity
- System operation information

Expected use in the project:
GSE is likely to be the main operational power system source.

Potential dashboard modules:
- Grid overview
- Generation trends
- Consumption trends
- Transmission/system context
- Installed capacity

Initial assessment:
High-priority source. GSE is important for operational and grid-related data.

Open questions:
- Is the data downloadable or only displayed on webpages?
- Are time series available?
- Are generation and consumption values available by month, day or hour?
- Can this source later support automated data collection?

## GENEX

Institution:
Georgian Energy Exchange.

Expected useful datasets:
- Day-ahead market reports
- Intraday market reports
- Trading summaries
- Price data
- Volume data
- Market participant information, if publicly available

Expected use in the project:
GENEX is relevant for the electricity market layer of the dashboard.

Potential dashboard modules:
- Day-ahead market prices
- Traded volumes
- Market activity
- Market development timeline

Initial assessment:
Medium-to-high priority source. GENEX becomes more important once the project moves from physical system data to electricity market data.

Open questions:
- What market data is publicly available?
- Are prices and volumes downloadable?
- Are reports in Georgian only?
- Is historical market data available in structured format?

## GNERC

Institution:
Georgian National Energy and Water Supply Regulatory Commission.

Expected useful datasets:
- Annual reports
- Electricity market reviews
- Regulatory decisions
- Tariff documents
- Market monitoring reports
- Licensing and regulatory information

Expected use in the project:
GNERC is mainly useful for regulatory context, market structure, tariffs and interpretation.

Potential dashboard modules:
- Market structure context
- Regulatory timeline
- Tariff and policy notes
- Sector overview

Initial assessment:
Medium-priority source. GNERC may not be the first source for dashboard data, but it is important for explaining the electricity market correctly.

Open questions:
- Which reports contain structured electricity market data?
- Are tables extractable from PDFs?
- Are reports available in English or only Georgian?
- Which documents are most useful for project documentation?

## Secondary Sources

Potential sources:
- Galt & Taggart electricity market reports
- Bank of Georgia research publications
- IEA Georgia energy profile
- Energy Community reports
- Other public analytical publications

Expected use in the project:
Secondary sources should support interpretation, not replace primary data.

Potential use cases:
- Explaining market trends
- Validating assumptions
- Understanding investment context
- Summarising sector developments
- Supporting LinkedIn posts with broader market context

Initial assessment:
Low-to-medium priority. Useful for communication and analysis, but not ideal as the core data foundation.

Open questions:
- Which secondary sources are updated regularly?
- Are charts and tables based on official data?
- Can they help identify gaps in primary sources?
- Are they suitable for citation in LinkedIn posts?

## Working Rules

1. Primary official sources should be used wherever possible.
2. Secondary sources can support interpretation but should not be the core dataset.
3. Every dataset added to the project should be documented in `data_catalog.csv`.
4. Original downloaded files should be stored in `data/raw/`.
5. Cleaned files should be stored in `data/processed/`.
6. Any manual transformation should be documented.
7. If a source is difficult to automate, start with manual download and document the process.
8. Do not build dashboard charts before confirming data quality.

## Immediate Next Source Audit Target

First target:
ESCO electricity balance or settlement indicator data.

Reason:
This is likely the strongest starting point for building a first manual dataset covering Georgia's electricity generation, consumption, imports and exports.