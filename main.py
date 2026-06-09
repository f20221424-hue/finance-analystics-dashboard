"""
Treasury Liquidity & Funding Analytics — Main Orchestrator

Run: python -m src.main  OR  python main.py (from project root)
"""

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_loader import populate_database, load_all_datasets
from src.database import clear_analytics_tables, init_database
from src.funding_gap import (
    compute_funding_gaps,
    daily_funding_gap_series,
    funding_concentration,
    store_funding_gap_results,
)
from src.lcr_calculator import (
    breach_alerts,
    calculate_lcr,
    monthly_average_lcr,
    plot_lcr_trend,
    store_lcr_results,
)
from src.nsfr_calculator import (
    calculate_nsfr,
    nsfr_trend_summary,
    plot_nsfr_trend,
    store_nsfr_results,
)
from src.reporting import (
    REPORTS_DIR,
    compute_management_metrics,
    export_powerbi_datasets,
    generate_funding_gap_report,
    generate_liquidity_report,
    generate_stress_test_report,
)
from src.stress_testing import run_all_stress_tests, store_stress_results

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("treasury_analytics")


def run_pipeline() -> None:
    charts_dir = PROJECT_ROOT / "reports" / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Step 1: Loading datasets")
    datasets = load_all_datasets()

    logger.info("Step 2: Populating database")
    engine = init_database()
    populate_database(engine)

    # Re-load from populated DB context using in-memory datasets
    balance_df = datasets["balance_sheet"]
    liquidity_df = datasets["liquidity_assets"]
    funding_df = datasets["funding_sources"]
    cashflow_df = datasets["cashflows"]

    clear_analytics_tables(engine)

    logger.info("Step 3: Calculating LCR")
    lcr_results_df = calculate_lcr(liquidity_df, cashflow_df, funding_df, balance_df)
    store_lcr_results(engine, lcr_results_df)
    plot_lcr_trend(lcr_results_df, charts_dir / "lcr_trend.png")
    logger.info(
        "LCR — Avg: %.2f%% | Min: %.2f%% | Breaches: %d",
        lcr_results_df["lcr"].mean(),
        lcr_results_df["lcr"].min(),
        len(breach_alerts(lcr_results_df)),
    )

    logger.info("Step 4: Calculating NSFR")
    nsfr_results_df = calculate_nsfr(funding_df, balance_df, liquidity_df)
    store_nsfr_results(engine, nsfr_results_df)
    plot_nsfr_trend(nsfr_results_df, charts_dir / "nsfr_trend.png")
    logger.info(
        "NSFR — Avg: %.2f%% | Min: %.2f%%",
        nsfr_results_df["nsfr"].mean(),
        nsfr_results_df["nsfr"].min(),
    )

    logger.info("Step 5: Running funding gap analysis")
    gap_daily = daily_funding_gap_series(funding_df, cashflow_df)
    store_funding_gap_results(engine, gap_daily)
    conc = funding_concentration(funding_df)
    logger.info(
        "Funding concentration — Top source: %s (%.1f%%)",
        conc.iloc[0]["funding_type"],
        conc.iloc[0]["concentration_pct"],
    )

    logger.info("Step 6: Running stress tests")
    stress_results = run_all_stress_tests(liquidity_df, funding_df, cashflow_df, balance_df)
    store_stress_results(engine, stress_results)
    for _, row in stress_results.iterrows():
        logger.info(
            "  %s — LCR: %.2f%% | NSFR: %.2f%% | Capital Impact: %s",
            row["scenario"],
            row["lcr"],
            row["nsfr"],
            f"{row['capital_impact']:,.0f}",
        )

    logger.info("Step 7: Generating reports")
    metrics = compute_management_metrics(
        engine, lcr_results_df, nsfr_results_df, funding_df, liquidity_df, balance_df
    )
    liq_report = generate_liquidity_report(engine, lcr_results_df, liquidity_df, metrics)
    stress_report = generate_stress_test_report(stress_results)
    gap_report = generate_funding_gap_report(gap_daily, funding_df)
    logger.info("Reports saved: %s, %s, %s", liq_report.name, stress_report.name, gap_report.name)

    logger.info("Step 8: Exporting Power BI datasets")
    pbi_dir = export_powerbi_datasets(engine)
    logger.info("Power BI datasets exported to %s", pbi_dir)

    _print_summary(metrics, lcr_results_df, nsfr_results_df, stress_results)


def _print_summary(metrics, lcr_df, nsfr_df, stress_df) -> None:
    print("\n" + "=" * 60)
    print("  TREASURY LIQUIDITY & FUNDING ANALYTICS — RUN COMPLETE")
    print("=" * 60)
    print(f"  Report Date:           {metrics['report_date']}")
    print(f"  Total Assets:          ${metrics['total_assets']:,.0f}")
    print(f"  Total HQLA:            ${metrics['total_hqla']:,.0f}")
    print(f"  Total Funding:         ${metrics['total_funding']:,.0f}")
    print(f"  Average LCR:           {metrics['average_lcr']:.2f}%")
    print(f"  Average NSFR:          {metrics['average_nsfr']:.2f}%")
    print(f"  Liquidity Buffer:      ${metrics['liquidity_buffer']:,.0f}")
    print(f"  LCR Breaches:          {metrics['regulatory_breaches_lcr']} days")
    print(f"  Largest Funding Source:{metrics['largest_funding_source']} ({metrics['funding_concentration_pct']:.1f}%)")
    print("-" * 60)
    print("  Stress Test LCR (Combined):", f"{stress_df.loc[stress_df['scenario']=='Combined Stress','lcr'].iloc[0]:.2f}%")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    run_pipeline()
