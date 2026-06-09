"""Treasury management reporting and Power BI dataset export."""

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils.dataframe import dataframe_to_rows
from sqlalchemy.engine import Engine

from .data_loader import read_table
from .funding_gap import funding_concentration, compute_maturity_ladder
from .lcr_calculator import breach_alerts, monthly_average_lcr
from .nsfr_calculator import nsfr_trend_summary
from .stress_testing import scenario_comparison_matrix

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
POWERBI_DIR = PROJECT_ROOT / "powerbi"


def _style_header(ws, row: int = 1) -> None:
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    for cell in ws[row]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")


def _write_df_to_sheet(ws, df: pd.DataFrame, title: str | None = None) -> None:
    if title:
        ws["A1"] = title
        ws["A1"].font = Font(bold=True, size=14)
        start_row = 3
    else:
        start_row = 1

    for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=True), start_row):
        for c_idx, value in enumerate(row, 1):
            ws.cell(row=r_idx, column=c_idx, value=value)
    _style_header(ws, start_row)


def compute_management_metrics(
    engine: Engine,
    lcr_df: pd.DataFrame,
    nsfr_df: pd.DataFrame,
    funding_df: pd.DataFrame,
    liquidity_df: pd.DataFrame,
    balance_df: pd.DataFrame,
) -> dict:
    """Aggregate key treasury management metrics."""
    conc = funding_concentration(funding_df)
    latest_bs = balance_df.sort_values("date").iloc[-1]
    hqla_total = liquidity_df.groupby("date")["amount"].sum().iloc[-1]

    return {
        "total_hqla": round(hqla_total, 2),
        "total_funding": round(funding_df["amount"].sum(), 2),
        "total_deposits": round(
            funding_df.loc[
                funding_df["funding_type"].str.contains("Deposit", case=False, na=False),
                "amount",
            ].sum(),
            2,
        ),
        "total_assets": round(latest_bs["total_assets"], 2),
        "total_deposits_bs": round(latest_bs["deposits"], 2),
        "average_lcr": round(lcr_df["lcr"].mean(), 2),
        "average_nsfr": round(nsfr_df["nsfr"].mean(), 2),
        "min_lcr": round(lcr_df["lcr"].min(), 2),
        "min_nsfr": round(nsfr_df["nsfr"].min(), 2),
        "largest_funding_source": conc.iloc[0]["funding_type"],
        "funding_concentration_pct": conc.iloc[0]["concentration_pct"],
        "liquidity_buffer": round(lcr_df["liquidity_buffer"].iloc[-1], 2),
        "regulatory_breaches_lcr": int((lcr_df["status"] != "Green").sum()),
        "regulatory_breaches_nsfr": int((nsfr_df["status"] == "Breach").sum()),
        "report_date": str(latest_bs["date"].date() if hasattr(latest_bs["date"], "date") else latest_bs["date"]),
    }


def generate_liquidity_report(
    engine: Engine,
    lcr_df: pd.DataFrame,
    liquidity_df: pd.DataFrame,
    metrics: dict,
    output_path: Path | None = None,
) -> Path:
    path = output_path or REPORTS_DIR / "liquidity_report.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws_summary = wb.active
    ws_summary.title = "Executive Summary"
    summary_df = pd.DataFrame([metrics]).T.reset_index()
    summary_df.columns = ["Metric", "Value"]
    _write_df_to_sheet(ws_summary, summary_df, "Treasury Liquidity Report")

    ws_lcr = wb.create_sheet("Daily LCR")
    _write_df_to_sheet(ws_lcr, lcr_df)

    ws_monthly = wb.create_sheet("Monthly LCR")
    _write_df_to_sheet(ws_monthly, monthly_average_lcr(lcr_df))

    ws_breaches = wb.create_sheet("Breach Alerts")
    _write_df_to_sheet(ws_breaches, breach_alerts(lcr_df))

    hqla_comp = (
        liquidity_df.groupby(["date", "asset_type"], as_index=False)["amount"]
        .sum()
        .groupby("asset_type")["amount"]
        .mean()
        .reset_index()
        .rename(columns={"amount": "avg_daily_amount"})
        .sort_values("avg_daily_amount", ascending=False)
    )
    ws_hqla = wb.create_sheet("HQLA Composition")
    _write_df_to_sheet(ws_hqla, hqla_comp)

    wb.save(path)
    return path


def generate_stress_test_report(
    stress_df: pd.DataFrame,
    output_path: Path | None = None,
) -> Path:
    path = output_path or REPORTS_DIR / "stress_test_report.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Stress Scenarios"
    display_df = stress_df.copy()
    if "description" in display_df.columns:
        cols = ["scenario", "description", "lcr", "nsfr", "funding_gap", "capital_impact", "hqla_stressed", "deposits_stressed"]
        display_df = display_df[[c for c in cols if c in display_df.columns]]
    _write_df_to_sheet(ws, display_df, "Treasury Stress Test Results")

    ws_matrix = wb.create_sheet("Scenario Matrix")
    _write_df_to_sheet(ws_matrix, scenario_comparison_matrix(stress_df).reset_index())

    wb.save(path)
    return path


def generate_funding_gap_report(
    gap_df: pd.DataFrame,
    funding_df: pd.DataFrame,
    output_path: Path | None = None,
) -> Path:
    path = output_path or REPORTS_DIR / "funding_gap_report.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws_gap = wb.active
    ws_gap.title = "Funding Gaps"
    latest_date = gap_df["date"].max()
    latest_gap = gap_df[gap_df["date"] == latest_date]
    _write_df_to_sheet(ws_gap, latest_gap, f"Funding Gap Analysis — {latest_date}")

    ws_ladder = wb.create_sheet("Maturity Ladder")
    _write_df_to_sheet(ws_ladder, compute_maturity_ladder(funding_df))

    ws_conc = wb.create_sheet("Concentration Risk")
    _write_df_to_sheet(ws_conc, funding_concentration(funding_df))

    wb.save(path)
    return path


def export_powerbi_datasets(engine: Engine) -> Path:
    """
    Export flattened datasets for Power BI import.

  Note: .pbix files are binary; this exports CSV datasets and a setup guide.
    """
    POWERBI_DIR.mkdir(parents=True, exist_ok=True)

    tables = [
        "balance_sheet",
        "liquidity_assets",
        "funding_sources",
        "cashflows",
        "lcr_results",
        "nsfr_results",
        "stress_tests",
        "funding_gap_results",
    ]

    for table in tables:
        df = read_table(engine, table)
        df.to_csv(POWERBI_DIR / f"{table}.csv", index=False)

    # Executive KPI summary for Power BI card visuals
    lcr = read_table(engine, "lcr_results")
    nsfr = read_table(engine, "nsfr_results")
    bs = read_table(engine, "balance_sheet")
    funding = read_table(engine, "funding_sources")

    latest_bs = bs.sort_values("date").iloc[-1]
    conc = funding_concentration(funding)

    kpi = pd.DataFrame(
        [
            {
                "report_date": latest_bs["date"],
                "total_assets": latest_bs["total_assets"],
                "total_deposits": latest_bs["deposits"],
                "lcr": lcr.iloc[-1]["lcr"],
                "nsfr": nsfr.iloc[-1]["nsfr"],
                "liquidity_buffer": lcr.iloc[-1]["liquidity_buffer"],
                "largest_funding_source": conc.iloc[0]["funding_type"],
                "funding_concentration_pct": conc.iloc[0]["concentration_pct"],
            }
        ]
    )
    kpi.to_csv(POWERBI_DIR / "executive_kpis.csv", index=False)

    _write_powerbi_setup_guide()
    return POWERBI_DIR


def _write_powerbi_setup_guide() -> None:
    guide = POWERBI_DIR / "POWERBI_SETUP.md"
    guide.write_text(
        """# Power BI Dashboard Setup Guide

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
""",
        encoding="utf-8",
    )
