"""Load CSV datasets and populate the treasury database."""

from pathlib import Path

import pandas as pd
from sqlalchemy.engine import Engine

from .database import (
    balance_sheet,
    cashflows,
    clear_source_tables,
    funding_sources,
    liquidity_assets,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    return df


def load_balance_sheet(data_dir: Path | None = None) -> pd.DataFrame:
    path = (data_dir or DATA_DIR) / "balance_sheet.csv"
    df = pd.read_csv(path, parse_dates=["Date"])
    return _normalize_columns(df)


def load_liquidity_assets(data_dir: Path | None = None) -> pd.DataFrame:
    path = (data_dir or DATA_DIR) / "liquidity_assets.csv"
    df = pd.read_csv(path, parse_dates=["Date"])
    return _normalize_columns(df)


def load_funding_sources(data_dir: Path | None = None) -> pd.DataFrame:
    path = (data_dir or DATA_DIR) / "funding_sources.csv"
    df = pd.read_csv(path)
    return _normalize_columns(df)


def load_cashflows(data_dir: Path | None = None) -> pd.DataFrame:
    path = (data_dir or DATA_DIR) / "cashflows.csv"
    df = pd.read_csv(path, parse_dates=["Date"])
    return _normalize_columns(df)


def load_all_datasets(data_dir: Path | None = None) -> dict[str, pd.DataFrame]:
    return {
        "balance_sheet": load_balance_sheet(data_dir),
        "liquidity_assets": load_liquidity_assets(data_dir),
        "funding_sources": load_funding_sources(data_dir),
        "cashflows": load_cashflows(data_dir),
    }


def populate_database(engine: Engine, data_dir: Path | None = None) -> dict[str, pd.DataFrame]:
    """Load CSV files and insert into SQL tables."""
    datasets = load_all_datasets(data_dir)
    clear_source_tables(engine)

    with engine.begin() as conn:
        datasets["balance_sheet"].to_sql(
            balance_sheet.name,
            conn,
            if_exists="append",
            index=False,
            method="multi",
        )
        datasets["liquidity_assets"].to_sql(
            liquidity_assets.name,
            conn,
            if_exists="append",
            index=False,
            method="multi",
        )
        datasets["funding_sources"].to_sql(
            funding_sources.name,
            conn,
            if_exists="append",
            index=False,
            method="multi",
        )
        datasets["cashflows"].to_sql(
            cashflows.name,
            conn,
            if_exists="append",
            index=False,
            method="multi",
        )

    return datasets


def read_table(engine: Engine, table_name: str) -> pd.DataFrame:
    df = pd.read_sql(f"SELECT * FROM {table_name}", engine)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df
