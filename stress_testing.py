"""Treasury liquidity stress testing scenarios."""

import pandas as pd
from sqlalchemy.engine import Engine

from .database import stress_tests
from .funding_gap import compute_funding_gaps
from .lcr_calculator import calculate_lcr, compute_adjusted_hqla
from .nsfr_calculator import calculate_nsfr

SCENARIOS = {
    "Market Stress": {
        "hqla_shock": -0.20,
        "deposit_shock": 0.0,
        "rate_shock_bps": 0,
        "description": "20% decline in HQLA market values",
    },
    "Deposit Run": {
        "hqla_shock": 0.0,
        "deposit_shock": -0.15,
        "rate_shock_bps": 0,
        "description": "15% withdrawal of customer deposits",
    },
    "Interest Rate Shock": {
        "hqla_shock": 0.0,
        "deposit_shock": 0.0,
        "rate_shock_bps": 300,
        "description": "+300bps parallel shift in interest rates",
    },
    "Combined Stress": {
        "hqla_shock": -0.20,
        "deposit_shock": -0.15,
        "rate_shock_bps": 0,
        "description": "Market stress combined with deposit run",
    },
}


def _apply_hqla_shock(liquidity_df: pd.DataFrame, shock: float) -> pd.DataFrame:
    df = liquidity_df.copy()
    df["amount"] = df["amount"] * (1 + shock)
    return df


def _apply_deposit_shock(funding_df: pd.DataFrame, shock: float) -> pd.DataFrame:
    df = funding_df.copy()
    deposit_mask = df["funding_type"].str.contains("Deposit", case=False, na=False)
    df.loc[deposit_mask, "amount"] = df.loc[deposit_mask, "amount"] * (1 + shock)
    return df


def _apply_rate_shock(funding_df: pd.DataFrame, bps: int) -> pd.DataFrame:
    df = funding_df.copy()
    shift = bps / 10_000
    df["interest_rate"] = df["interest_rate"] + shift
    return df


def _capital_impact(
    balance_df: pd.DataFrame,
    funding_df: pd.DataFrame,
    rate_shock_bps: int,
    deposit_shock: float,
) -> float:
    """Estimate capital impact from NII compression and deposit loss."""
    if balance_df.empty:
        return 0.0

    latest = balance_df.sort_values("date").iloc[-1]
    capital = latest.get("capital", 0)
    deposits = funding_df.loc[
        funding_df["funding_type"].str.contains("Deposit", case=False, na=False),
        "amount",
    ].sum()

    deposit_loss = deposits * abs(deposit_shock) * 0.05  # 5% loss given default proxy
    nii_impact = latest.get("loans", 0) * (rate_shock_bps / 10_000) * 0.25  # partial repricing
    total_impact = deposit_loss + nii_impact
    return round(-total_impact, 2)


def run_stress_scenario(
    scenario_name: str,
    params: dict,
    liquidity_df: pd.DataFrame,
    funding_df: pd.DataFrame,
    cashflow_df: pd.DataFrame,
    balance_df: pd.DataFrame,
    reference_date: pd.Timestamp | None = None,
) -> dict:
    """Run a single stress scenario and return impacted metrics."""
    ref_date = reference_date or pd.to_datetime(liquidity_df["date"].max())

    stressed_liq = _apply_hqla_shock(liquidity_df, params["hqla_shock"])
    stressed_funding = _apply_deposit_shock(funding_df, params["deposit_shock"])
    stressed_funding = _apply_rate_shock(stressed_funding, params["rate_shock_bps"])

    # Stressed cashflows: deposit run increases outflows
    stressed_cf = cashflow_df.copy()
    if params["deposit_shock"] != 0:
        stressed_cf["expected_outflows"] *= 1 + abs(params["deposit_shock"]) * 0.5

    lcr_res = calculate_lcr(stressed_liq, stressed_cf, stressed_funding, balance_df)
    nsfr_res = calculate_nsfr(stressed_funding, balance_df, stressed_liq)
    gap_res = compute_funding_gaps(stressed_funding, stressed_cf, ref_date)

    lcr_latest = lcr_res[lcr_res["date"] == ref_date]
    if lcr_latest.empty:
        lcr_latest = lcr_res.iloc[-1:]
    nsfr_latest = nsfr_res[nsfr_res["date"] == ref_date]
    if nsfr_latest.empty:
        nsfr_latest = nsfr_res.iloc[-1:]

    hqla_stressed = compute_adjusted_hqla(stressed_liq)
    hqla_val = hqla_stressed[hqla_stressed["date"] == ref_date]["hqla"]
    if hqla_val.empty:
        hqla_val = hqla_stressed.iloc[-1]["hqla"]
    else:
        hqla_val = hqla_val.iloc[0]

    deposits_stressed = stressed_funding.loc[
        stressed_funding["funding_type"].str.contains("Deposit", case=False, na=False),
        "amount",
    ].sum()

    return {
        "scenario": scenario_name,
        "date": ref_date,
        "lcr": round(float(lcr_latest["lcr"].iloc[0]), 2),
        "nsfr": round(float(nsfr_latest["nsfr"].iloc[0]), 2),
        "funding_gap": round(float(gap_res["funding_gap"].sum()), 2),
        "capital_impact": _capital_impact(
            balance_df, funding_df, params["rate_shock_bps"], params["deposit_shock"]
        ),
        "hqla_stressed": round(float(hqla_val), 2),
        "deposits_stressed": round(float(deposits_stressed), 2),
        "description": params["description"],
    }


def run_all_stress_tests(
    liquidity_df: pd.DataFrame,
    funding_df: pd.DataFrame,
    cashflow_df: pd.DataFrame,
    balance_df: pd.DataFrame,
) -> pd.DataFrame:
    results = []
    ref_date = pd.to_datetime(liquidity_df["date"].max())
    for name, params in SCENARIOS.items():
        result = run_stress_scenario(
            name, params, liquidity_df, funding_df, cashflow_df, balance_df, ref_date
        )
        results.append(result)
    return pd.DataFrame(results)


def store_stress_results(engine: Engine, results: pd.DataFrame) -> None:
    export_cols = [
        "scenario",
        "date",
        "lcr",
        "nsfr",
        "funding_gap",
        "capital_impact",
        "hqla_stressed",
        "deposits_stressed",
    ]
    with engine.begin() as conn:
        results[export_cols].to_sql(stress_tests.name, conn, if_exists="replace", index=False)


def scenario_comparison_matrix(results: pd.DataFrame) -> pd.DataFrame:
    """Pivot stress results for heatmap-style analysis."""
    base_lcr = results.loc[results["scenario"] == "Market Stress", "lcr"]
    # Use first scenario baseline from unstressed if available
    matrix = results.set_index("scenario")[["lcr", "nsfr", "funding_gap", "capital_impact"]]
    return matrix.round(2)
