"""Net Stable Funding Ratio (NSFR) calculation module."""

import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy.engine import Engine

from .database import nsfr_results

# Available Stable Funding (ASF) factors by funding type
ASF_FACTORS = {
    "Retail Deposits": 0.95,
    "Corporate Deposits": 0.50,
    "Wholesale Funding": 0.50,
    "Interbank Borrowings": 0.00,
    "Senior Debt": 1.00,
    "Subordinated Debt": 1.00,
    "Tier 1 Capital": 1.00,
}

# Required Stable Funding (RSF) factors by asset/liability category
RSF_FACTORS = {
    "cash": 0.00,
    "hqla": 0.05,
    "loans": 0.85,
    "other_assets": 0.50,
    "off_balance": 0.00,
}


def _asf_factor(funding_type: str) -> float:
    for key, factor in ASF_FACTORS.items():
        if key.lower() in funding_type.lower():
            return factor
    return 0.50


def compute_available_stable_funding(funding_df: pd.DataFrame) -> float:
    asf = 0.0
    for _, row in funding_df.iterrows():
        factor = _asf_factor(row["funding_type"])
        # Maturity adjustment: shorter maturity reduces stability
        maturity_days = row.get("maturity_days", 365)
        if maturity_days <= 30:
            factor *= 0.50
        elif maturity_days <= 90:
            factor *= 0.75
        asf += row["amount"] * factor
    return asf


def compute_required_stable_funding(
    balance_df: pd.DataFrame,
    liquidity_df: pd.DataFrame,
) -> float:
    """Compute RSF based on latest balance sheet and HQLA composition."""
    if balance_df.empty:
        return 1.0

    latest = balance_df.sort_values("date").iloc[-1]
    hqla_total = liquidity_df.groupby("asset_type")["amount"].sum().sum()

    rsf = 0.0
    rsf += latest.get("loans", 0) * RSF_FACTORS["loans"]
    rsf += hqla_total * RSF_FACTORS["hqla"]
    rsf += latest.get("assets", 0) * RSF_FACTORS["other_assets"]
    rsf += latest.get("capital", 0) * 0.00  # capital is ASF, not RSF
    return max(rsf, 1.0)


def _nsfr_status(nsfr: float) -> str:
    return "Compliant" if nsfr >= 100 else "Breach"


def calculate_nsfr(
    funding_df: pd.DataFrame,
    balance_df: pd.DataFrame,
    liquidity_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Calculate daily NSFR.

    ASF is relatively stable across days; RSF varies with balance sheet evolution.
    """
    asf = compute_available_stable_funding(funding_df)

    rows = []
    for _, bs_row in balance_df.iterrows():
        date = bs_row["date"]
        liq_slice = liquidity_df[liquidity_df["date"] == date]
        rsf = compute_required_stable_funding(
            balance_df[balance_df["date"] == date],
            liq_slice if not liq_slice.empty else liquidity_df,
        )
        nsfr = (asf / rsf) * 100 if rsf > 0 else 0.0
        rows.append(
            {
                "date": date,
                "available_stable_funding": round(asf, 2),
                "required_stable_funding": round(rsf, 2),
                "nsfr": round(nsfr, 2),
                "status": _nsfr_status(nsfr),
            }
        )

    return pd.DataFrame(rows)


def store_nsfr_results(engine: Engine, results: pd.DataFrame) -> None:
    with engine.begin() as conn:
        results.to_sql(nsfr_results.name, conn, if_exists="replace", index=False)


def nsfr_trend_summary(results: pd.DataFrame) -> pd.DataFrame:
    df = results.copy()
    df["month"] = pd.to_datetime(df["date"]).dt.to_period("M").astype(str)
    return (
        df.groupby("month", as_index=False)
        .agg(
            avg_nsfr=("nsfr", "mean"),
            min_nsfr=("nsfr", "min"),
            breach_days=("status", lambda s: (s == "Breach").sum()),
        )
        .round(2)
    )


def plot_nsfr_trend(results: pd.DataFrame, output_path: str | None = None) -> None:
    fig, ax = plt.subplots(figsize=(12, 5))
    dates = pd.to_datetime(results["date"])
    ax.plot(dates, results["nsfr"], color="#2e75b6", linewidth=1.2, label="Daily NSFR")
    ax.axhline(100, color="green", linestyle="--", linewidth=1, label="Regulatory Minimum (100%)")
    ax.set_title("Net Stable Funding Ratio (NSFR) Trend", fontsize=14, fontweight="bold")
    ax.set_xlabel("Date")
    ax.set_ylabel("NSFR (%)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    if output_path:
        plt.savefig(output_path, dpi=150)
        plt.close()
    else:
        plt.show()
