"""Funding gap analysis by maturity bucket."""

import pandas as pd
from sqlalchemy.engine import Engine

from .database import funding_gap_results

MATURITY_BUCKETS = [
    ("0-30 Days", 0, 30),
    ("31-90 Days", 31, 90),
    ("91-180 Days", 91, 180),
    ("180-365 Days", 181, 365),
    ("1+ Years", 366, 99999),
]


def _assign_bucket(days: int) -> str:
    for label, low, high in MATURITY_BUCKETS:
        if low <= days <= high:
            return label
    return "1+ Years"


def _gap_status(gap: float) -> str:
    if gap > 0:
        return "Positive"
    if gap < 0:
        return "Negative"
    return "Neutral"


def compute_maturity_ladder(funding_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate funding sources into maturity buckets."""
    df = funding_df.copy()
    df["maturity_bucket"] = df["maturity_days"].apply(_assign_bucket)

    ladder = (
        df.groupby("maturity_bucket", as_index=False)
        .agg(
            total_funding=("amount", "sum"),
            avg_rate=("interest_rate", "mean"),
            source_count=("funding_type", "count"),
        )
    )

    bucket_order = [b[0] for b in MATURITY_BUCKETS]
    ladder["maturity_bucket"] = pd.Categorical(
        ladder["maturity_bucket"], categories=bucket_order, ordered=True
    )
    return ladder.sort_values("maturity_bucket")


def compute_funding_gaps(
    funding_df: pd.DataFrame,
    cashflow_df: pd.DataFrame,
    reference_date: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """
    Calculate funding gap = Inflows - Outflows per maturity bucket.

    Inflows are proxied by maturing liabilities (funding returning to bank)
    and expected cash inflows. Outflows are proxied by funding needs and
    expected cash outflows scaled to bucket horizons.
    """
    ref_date = reference_date or pd.to_datetime(cashflow_df["date"].max())
    cf_day = cashflow_df[cashflow_df["date"] == ref_date]
    if cf_day.empty:
        cf_day = cashflow_df.groupby("date").sum(numeric_only=True).iloc[-1:]

    total_inflows = cf_day["expected_inflows"].sum() if "expected_inflows" in cf_day.columns else 0
    total_outflows = cf_day["expected_outflows"].sum() if "expected_outflows" in cf_day.columns else 0

    df = funding_df.copy()
    df["maturity_bucket"] = df["maturity_days"].apply(_assign_bucket)

    bucket_funding = df.groupby("maturity_bucket")["amount"].sum()
    n_buckets = len(MATURITY_BUCKETS)

    rows = []
    for label, low, high in MATURITY_BUCKETS:
        bucket_weight = (high - low + 1) / 365 if high < 99999 else 0.35
        inflows = bucket_funding.get(label, 0) * 0.6 + total_inflows * bucket_weight
        outflows = bucket_funding.get(label, 0) * 0.4 + total_outflows * bucket_weight
        gap = inflows - outflows
        rows.append(
            {
                "date": ref_date,
                "maturity_bucket": label,
                "inflows": round(inflows, 2),
                "outflows": round(outflows, 2),
                "funding_gap": round(gap, 2),
                "gap_status": _gap_status(gap),
            }
        )

    return pd.DataFrame(rows)


def funding_concentration(funding_df: pd.DataFrame) -> pd.DataFrame:
    """Identify concentration risk in funding sources."""
    total = funding_df["amount"].sum()
    conc = (
        funding_df.groupby("funding_type", as_index=False)
        .agg(amount=("amount", "sum"))
        .assign(concentration_pct=lambda x: (x["amount"] / total * 100).round(2))
        .sort_values("amount", ascending=False)
    )
    conc["risk_flag"] = conc["concentration_pct"].apply(
        lambda p: "High" if p > 25 else ("Medium" if p > 15 else "Low")
    )
    return conc


def store_funding_gap_results(engine: Engine, results: pd.DataFrame) -> None:
    with engine.begin() as conn:
        results.to_sql(funding_gap_results.name, conn, if_exists="replace", index=False)


def daily_funding_gap_series(
    funding_df: pd.DataFrame,
    cashflow_df: pd.DataFrame,
) -> pd.DataFrame:
    """Generate funding gap snapshots for each date in cashflow data."""
    all_results = []
    for date in cashflow_df["date"].unique():
        gap = compute_funding_gaps(funding_df, cashflow_df, pd.Timestamp(date))
        all_results.append(gap)
    return pd.concat(all_results, ignore_index=True)
