# Power BI Dashboard Setup Guide

## Data Source
Import all CSV files from the `powerbi/` folder into Power BI Desktop.

Recommended import order:
1. `executive_kpis.csv` — KPI cards
2. `lcr_results.csv` — LCR trend line chart
3. `nsfr_results.csv` — NSFR trend line chart
4. `liquidity_assets.csv` — HQLA composition (stacked bar / donut)
5. `funding_sources.csv` — Funding mix (treemap)
6. `funding_gap_results.csv` — Gap waterfall / bar chart
7. `stress_tests.csv` — Scenario comparison clustered bar
8. `balance_sheet.csv` — Total assets trend
9. `cashflows.csv` — Inflow/outflow by business unit

## Dashboard Pages

### Page 1: Executive Summary
- Card visuals: Total Assets, Total Deposits, LCR, NSFR, Liquidity Buffer
- Line chart: Daily LCR (lcr_results)
- Gauge: LCR vs 100% minimum

### Page 2: Liquidity Dashboard
- Line chart: Daily LCR trend with 90%/100% reference lines
- Donut chart: HQLA composition by asset_type
- Area chart: Liquidity buffer over time

### Page 3: Funding Dashboard
- Treemap: Funding mix by funding_type
- Bar chart: Funding concentration %
- Waterfall: Funding gap by maturity_bucket
- Column chart: Maturity ladder

### Page 4: Stress Testing
- Clustered bar: LCR and NSFR by scenario
- Table: Full stress test results
- Matrix/heatmap: Scenario comparison (conditional formatting)

### Page 5: Treasury Risk
- Table: LCR breach alerts (status != Green)
- Card: Regulatory breach count
- Line charts: LCR and NSFR trends
- KPI: Funding concentration risk flag

## DAX Measures (Examples)

```dax
LCR Average = AVERAGE(lcr_results[lcr])
NSFR Average = AVERAGE(nsfr_results[nsfr])
LCR Breach Count = COUNTROWS(FILTER(lcr_results, lcr_results[status] <> "Green"))
Liquidity Buffer Latest = MAX(lcr_results[liquidity_buffer])
```

## Refresh
Re-run `python main.py` to regenerate CSV exports, then Refresh in Power BI.
