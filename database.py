"""SQLAlchemy database schema and connection management."""

from pathlib import Path

from sqlalchemy import (
    Column,
    Date,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    text,
)
from sqlalchemy.engine import Engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "database" / "treasury.db"

metadata = MetaData()

balance_sheet = Table(
    "balance_sheet",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("date", Date, nullable=False),
    Column("assets", Float),
    Column("liabilities", Float),
    Column("deposits", Float),
    Column("loans", Float),
    Column("capital", Float),
    Column("total_assets", Float),
    Column("total_liabilities", Float),
)

liquidity_assets = Table(
    "liquidity_assets",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("date", Date, nullable=False),
    Column("asset_type", String(64)),
    Column("amount", Float),
    Column("hqla_category", String(32)),
)

funding_sources = Table(
    "funding_sources",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("funding_type", String(64)),
    Column("amount", Float),
    Column("maturity", String(64)),
    Column("maturity_days", Integer),
    Column("interest_rate", Float),
)

cashflows = Table(
    "cashflows",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("date", Date, nullable=False),
    Column("expected_inflows", Float),
    Column("expected_outflows", Float),
    Column("business_unit", String(64)),
)

lcr_results = Table(
    "lcr_results",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("date", Date, nullable=False, unique=True),
    Column("hqla", Float),
    Column("net_cash_outflows", Float),
    Column("lcr", Float),
    Column("status", String(16)),
    Column("liquidity_buffer", Float),
)

nsfr_results = Table(
    "nsfr_results",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("date", Date, nullable=False, unique=True),
    Column("available_stable_funding", Float),
    Column("required_stable_funding", Float),
    Column("nsfr", Float),
    Column("status", String(16)),
)

stress_tests = Table(
    "stress_tests",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("scenario", String(64)),
    Column("date", Date),
    Column("lcr", Float),
    Column("nsfr", Float),
    Column("funding_gap", Float),
    Column("capital_impact", Float),
    Column("hqla_stressed", Float),
    Column("deposits_stressed", Float),
)

funding_gap_results = Table(
    "funding_gap_results",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("date", Date, nullable=False),
    Column("maturity_bucket", String(32)),
    Column("inflows", Float),
    Column("outflows", Float),
    Column("funding_gap", Float),
    Column("gap_status", String(16)),
)


def get_engine(db_path: Path | None = None) -> Engine:
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{path}", echo=False)


def init_database(engine: Engine | None = None) -> Engine:
    eng = engine or get_engine()
    metadata.create_all(eng)
    return eng


def clear_analytics_tables(engine: Engine) -> None:
    """Clear computed result tables before recalculation."""
    with engine.begin() as conn:
        for table in (
            "lcr_results",
            "nsfr_results",
            "stress_tests",
            "funding_gap_results",
        ):
            conn.execute(text(f"DELETE FROM {table}"))


def clear_source_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        for table in (
            "balance_sheet",
            "liquidity_assets",
            "funding_sources",
            "cashflows",
        ):
            conn.execute(text(f"DELETE FROM {table}"))
