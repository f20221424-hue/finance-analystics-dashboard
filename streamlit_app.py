"""Optional Streamlit dashboard for Treasury Analytics."""

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "database" / "treasury.db"


@st.cache_resource
def get_engine():
    return create_engine(f"sqlite:///{DB_PATH}")


def load(table: str) -> pd.DataFrame:
    return pd.read_sql_table(table, get_engine(), parse_dates=["date"])


def main() -> None:
    st.set_page_config(page_title="Treasury Analytics", layout="wide")
    st.title("Treasury Liquidity & Funding Analytics")

    if not DB_PATH.exists():
        st.warning("Database not found. Run `python main.py` first.")
        return

    lcr = load("lcr_results")
    nsfr = load("nsfr_results")
    stress = load("stress_tests")
    gap = load("funding_gap_results")
    funding = load("funding_sources")
    liquidity = load("liquidity_assets")
    bs = load("balance_sheet")

    latest_bs = bs.sort_values("date").iloc[-1]
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Assets", f"${latest_bs['total_assets']/1e9:.1f}B")
    col2.metric("LCR", f"{lcr.iloc[-1]['lcr']:.1f}%")
    col3.metric("NSFR", f"{nsfr.iloc[-1]['nsfr']:.1f}%")
    col4.metric("Liquidity Buffer", f"${lcr.iloc[-1]['liquidity_buffer']/1e9:.2f}B")
    col5.metric("LCR Breaches", f"{(lcr['status'] != 'Green').sum()} days")

    tab1, tab2, tab3, tab4 = st.tabs(["Liquidity", "Funding", "Stress Tests", "Risk"])

    with tab1:
        fig_lcr = px.line(lcr, x="date", y="lcr", title="Daily LCR Trend")
        fig_lcr.add_hline(y=100, line_dash="dash", annotation_text="100% Minimum")
        fig_lcr.add_hline(y=90, line_dash="dot", annotation_text="90% Warning")
        st.plotly_chart(fig_lcr, use_container_width=True)

        hqla_avg = liquidity.groupby("asset_type")["amount"].mean().reset_index()
        st.plotly_chart(
            px.pie(hqla_avg, names="asset_type", values="amount", title="HQLA Composition"),
            use_container_width=True,
        )

    with tab2:
        st.plotly_chart(
            px.bar(funding, x="funding_type", y="amount", title="Funding Mix", color="funding_type"),
            use_container_width=True,
        )
        latest_gap = gap[gap["date"] == gap["date"].max()]
        st.plotly_chart(
            px.bar(latest_gap, x="maturity_bucket", y="funding_gap", color="gap_status", title="Funding Gap by Maturity"),
            use_container_width=True,
        )

    with tab3:
        st.plotly_chart(
            px.bar(stress, x="scenario", y=["lcr", "nsfr"], barmode="group", title="Stress Scenario Impact"),
            use_container_width=True,
        )
        st.dataframe(stress)

    with tab4:
        breaches = lcr[lcr["status"] != "Green"]
        st.subheader("LCR Breach Alerts")
        st.dataframe(breaches[["date", "lcr", "status", "liquidity_buffer"]])


if __name__ == "__main__":
    main()
