"""Liquidity Coverage Ratio (LCR) calculation module."""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sqlalchemy.engine import Engine

from .database import lcr_results

# Basel III HQLA haircuts (simplified)
HQLA_FACTORS = {
    "Level 1": 1.00,
    "Level 2A": 0.85,
    "Level 2B": 0.50,
}

# Retail deposit runoff rates for 30-day net cash outflows (simplified)
OUTFLOW_RATES = {
    "retail_stable": 0.05,
    "retail_less_stable": 0.10,
    "corporate_operational": 0.25,
    "corporate_non_operational": 0.40,
    "wholesale": 0.50,
    "interbank": 1.00,
}


def _hqla_haircut(category: str) -> float:
    return HQLA_FACTORS.get(category, 0.50)


def compute_adjusted_hqla(liquidity_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate daily adjusted HQLA after regulatory haircuts."""
    df = liquidity_df.copy()
    df["adjusted_amount"] = df["amount"] * df["hqla_category"].map(_hqla_haircut)
    daily = (
        df.groupby("date", as_index=False)["adjusted_amount"]
        .sum()
        .rename(columns={"adjusted_amount": "hqla"})
    )
    return daily


def compute_net_cash_outflows(
    cashflow_df: pd.DataFrame,
    funding_df: pd.DataFrame,
    balance_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Estimate 30-day net cash outflows per Basel III LCR framework (simplified).

    Combines contractual outflows from cashflow projections with
    behavioural runoff on deposit funding.
    """
    daily_cf = (
        cashflow_df.groupby("date", as_index=False)
        .agg(
            expected_inflows=("expected_inflows", "sum"),
            expected_outflows=("expected_outflows", "sum"),
        )
    )

    total_deposits = funding_df.loc[
        funding_df["funding_type"].str.contains("Deposit", case=False, na=False),
        "amount",
    ].sum()

    deposit_runoff = 0.0
    for _, row in funding_df.iterrows():
        ft = row["funding_type"].lower()
        if "retail" in ft and "stable" in str(row.get("maturity", "")).lower():
            deposit_runoff += row["amount"] * OUTFLOW_RATES["retail_stable"]
        elif "retail" in ft:
            deposit_runoff += row["amount"] * OUTFLOW_RATES["retail_less_stable"]
        elif "corporate" in ft:
            deposit_runoff += row["amount"] * OUTFLOW_RATES["corporate_operational"]
        elif "wholesale" in ft:
            deposit_runoff += row["amount"] * OUTFLOW_RATES["wholesale"]
        elif "interbank" in ft:
            deposit_runoff += row["amount"] * OUTFLOW_RATES["interbank"]

    # Scale daily contractual outflows to a 30-day stress horizon (simplified Basel III)
    daily_cf["contractual_outflows_30d"] = daily_cf["expected_outflows"] * 12
    daily_cf["behavioural_outflows"] = deposit_runoff * 0.35
    daily_cf["total_inflows_30d"] = daily_cf["expected_inflows"] * 12 * 0.65

    daily_cf["net_cash_outflows"] = np.maximum(
        daily_cf["contractual_outflows_30d"]
        + daily_cf["behavioural_outflows"]
        - daily_cf["total_inflows_30d"],
        daily_cf["expected_outflows"] * 12 * 0.20,
    )

    if not balance_df.empty:
        avg_assets = balance_df["total_assets"].mean()
        daily_cf["net_cash_outflows"] = daily_cf["net_cash_outflows"].clip(
            lower=avg_assets * 0.08,
            upper=avg_assets * 0.18,
        )

    return daily_cf[["date", "net_cash_outflows"]]


def _lcr_status(lcr: float) -> str:
    if lcr >= 100:
        return "Green"
    if lcr >= 90:
        return "Yellow"
    return "Red"


def calculate_lcr(
    liquidity_df: pd.DataFrame,
    cashflow_df: pd.DataFrame,
    funding_df: pd.DataFrame,
    balance_df: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate daily LCR = HQLA / Net Cash Outflows * 100."""
    hqla_daily = compute_adjusted_hqla(liquidity_df)
    outflows = compute_net_cash_outflows(cashflow_df, funding_df, balance_df)

    results = hqla_daily.merge(outflows, on="date", how="inner")
    results["lcr"] = (results["hqla"] / results["net_cash_outflows"]) * 100
    results["liquidity_buffer"] = results["hqla"] - results["net_cash_outflows"]
    results["status"] = results["lcr"].apply(_lcr_status)
    return results


def store_lcr_results(engine: Engine, results: pd.DataFrame) -> None:
    with engine.begin() as conn:
        results.to_sql(lcr_results.name, conn, if_exists="replace", index=False)


def monthly_average_lcr(results: pd.DataFrame) -> pd.DataFrame:
    df = results.copy()
    df["month"] = pd.to_datetime(df["date"]).dt.to_period("M").astype(str)
    return (
        df.groupby("month", as_index=False)
        .agg(
            avg_lcr=("lcr", "mean"),
            min_lcr=("lcr", "min"),
            max_lcr=("lcr", "max"),
            breach_days=("status", lambda s: (s != "Green").sum()),
        )
        .round(2)
    )


def breach_alerts(results: pd.DataFrame) -> pd.DataFrame:
    return results[results["status"] != "Green"].copy()


def plot_lcr_trend(results: pd.DataFrame, output_path: str | None = None) -> None:
    fig, ax = plt.subplots(figsize=(12, 5))
    dates = pd.to_datetime(results["date"])
    ax.plot(dates, results["lcr"], color="#1f4e79", linewidth=1.2, label="Daily LCR")
    ax.axhline(100, color="green", linestyle="--", linewidth=1, label="Regulatory Minimum (100%)")
    ax.axhline(90, color="orange", linestyle="--", linewidth=1, label="Warning Threshold (90%)")
    ax.fill_between(dates, 100, results["lcr"], where=results["lcr"] >= 100, alpha=0.15, color="green")
    ax.fill_between(dates, 90, results["lcr"], where=(results["lcr"] >= 90) & (results["lcr"] < 100), alpha=0.15, color="orange")
    ax.fill_between(dates, 0, results["lcr"], where=results["lcr"] < 90, alpha=0.15, color="red")
    ax.set_title("Daily Liquidity Coverage Ratio (LCR) Trend", fontsize=14, fontweight="bold")
    ax.set_xlabel("Date")
    ax.set_ylabel("LCR (%)")
    ax.legend(loc="lower right")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    if output_path:
        plt.savefig(output_path, dpi=150)
        plt.close()
    else:
        plt.show()
