"""Generate realistic banking sample datasets for Treasury Analytics."""

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

np.random.seed(42)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def _date_range(days: int = 365) -> list[str]:
    end = datetime(2025, 12, 31)
    start = end - timedelta(days=days - 1)
    return [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]


def generate_balance_sheet() -> pd.DataFrame:
    dates = _date_range(365)
    rows = []
    base_assets = 85_000_000_000
    for i, d in enumerate(dates):
        growth = 1 + 0.00015 * i + np.random.normal(0, 0.0008)
        total_assets = base_assets * growth
        loans = total_assets * np.random.uniform(0.58, 0.62)
        deposits = total_assets * np.random.uniform(0.42, 0.48)
        capital = total_assets * np.random.uniform(0.08, 0.10)
        other_assets = total_assets - loans - total_assets * 0.12
        other_liab = total_assets - deposits - capital
        rows.append(
            {
                "Date": d,
                "Assets": round(other_assets, 2),
                "Liabilities": round(other_liab, 2),
                "Deposits": round(deposits, 2),
                "Loans": round(loans, 2),
                "Capital": round(capital, 2),
                "Total_Assets": round(total_assets, 2),
                "Total_Liabilities": round(deposits + other_liab, 2),
            }
        )
    return pd.DataFrame(rows)


def generate_liquidity_assets() -> pd.DataFrame:
    dates = _date_range(365)
    asset_types = [
        ("Cash", "Level 1", 0.08),
        ("Government Bonds", "Level 1", 0.22),
        ("Treasury Bills", "Level 1", 0.10),
        ("Central Bank Reserves", "Level 1", 0.06),
        ("Corporate Bonds", "Level 2A", 0.05),
        ("Covered Bonds", "Level 2B", 0.03),
    ]
    rows = []
    base_hqla = 14_500_000_000
    for d in dates:
        daily_factor = np.random.uniform(0.97, 1.03)
        for asset_type, category, weight in asset_types:
            amount = base_hqla * weight * daily_factor * np.random.uniform(0.95, 1.05)
            rows.append(
                {
                    "Date": d,
                    "Asset_Type": asset_type,
                    "Amount": round(amount, 2),
                    "HQLA_Category": category,
                }
            )
    return pd.DataFrame(rows)


def generate_funding_sources() -> pd.DataFrame:
    funding_types = [
        ("Retail Deposits", 28_000_000_000, "Stable", 365, 0.015),
        ("Retail Deposits", 8_500_000_000, "Less Stable", 90, 0.022),
        ("Corporate Deposits", 12_000_000_000, "Operational", 180, 0.028),
        ("Wholesale Funding", 6_500_000_000, "Short-term", 60, 0.045),
        ("Interbank Borrowings", 4_200_000_000, "Overnight", 7, 0.038),
        ("Senior Debt", 5_800_000_000, "Long-term", 1825, 0.042),
        ("Subordinated Debt", 1_200_000_000, "Long-term", 2555, 0.055),
        ("Tier 1 Capital", 7_500_000_000, "Perpetual", 9999, 0.0),
    ]
    rows = []
    for ft, amount, maturity_label, days, rate in funding_types:
        rows.append(
            {
                "Funding_Type": ft,
                "Amount": round(amount * np.random.uniform(0.98, 1.02), 2),
                "Maturity": maturity_label,
                "Maturity_Days": days,
                "Interest_Rate": rate,
            }
        )
    return pd.DataFrame(rows)


def generate_cashflows() -> pd.DataFrame:
    dates = _date_range(365)
    units = ["Retail Banking", "Corporate Banking", "Markets", "Treasury", "Operations"]
    rows = []
    for d in dates:
        for unit in units:
            base_in = np.random.uniform(80_000_000, 250_000_000)
            base_out = np.random.uniform(70_000_000, 230_000_000)
            if unit == "Treasury":
                base_in *= 1.5
                base_out *= 1.4
            rows.append(
                {
                    "Date": d,
                    "Expected_Inflows": round(base_in, 2),
                    "Expected_Outflows": round(base_out, 2),
                    "Business_Unit": unit,
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    generate_balance_sheet().to_csv(DATA_DIR / "balance_sheet.csv", index=False)
    generate_liquidity_assets().to_csv(DATA_DIR / "liquidity_assets.csv", index=False)
    generate_funding_sources().to_csv(DATA_DIR / "funding_sources.csv", index=False)
    generate_cashflows().to_csv(DATA_DIR / "cashflows.csv", index=False)
    print(f"Sample data written to {DATA_DIR}")


if __name__ == "__main__":
    main()
