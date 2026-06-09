# Treasury Analytics — Technical Architecture

## System Context

The platform simulates a bank treasury department's daily liquidity and funding risk monitoring workflow. Source data flows from CSV files into a SQLite database, through regulatory calculation engines, and into Excel reports and Power BI datasets.

## Component Diagram

```mermaid
flowchart LR
    subgraph Sources
        BS[Balance Sheet]
        LA[Liquidity Assets]
        FS[Funding Sources]
        CF[Cash Flows]
    end

    subgraph Core["Analytics Core (Python)"]
        DL[data_loader]
        LCR[lcr_calculator]
        NSFR[nsfr_calculator]
        FG[funding_gap]
        ST[stress_testing]
        RP[reporting]
    end

    subgraph Storage
        SQL[(SQLite)]
    end

    subgraph Delivery
        XL[Excel Reports]
        PBI[Power BI CSVs]
        PNG[Chart PNGs]
    end

    BS & LA & FS & CF --> DL --> SQL
    SQL --> LCR & NSFR & FG & ST
    LCR & NSFR & FG & ST --> SQL
    LCR & NSFR & FG & ST --> RP
    RP --> XL & PBI & PNG
```

## Module Responsibilities

| Module | Responsibility |
|---|---|
| `database.py` | SQLAlchemy schema, engine, table definitions |
| `data_loader.py` | CSV ingestion, DB population, table reads |
| `lcr_calculator.py` | HQLA haircuts, net cash outflows, daily LCR |
| `nsfr_calculator.py` | ASF/RSF factors, daily NSFR |
| `funding_gap.py` | Maturity buckets, gap analysis, concentration |
| `stress_testing.py` | Four regulatory stress scenarios |
| `reporting.py` | Excel workbooks, Power BI exports |
| `main.py` | End-to-end orchestration |

## Regulatory Calculation Logic

### LCR

1. Apply HQLA haircuts by asset category (Level 1/2A/2B)
2. Estimate 30-day net cash outflows from contractual flows + deposit runoff
3. Cap inflows at 65% of outflows (Basel simplified)
4. `LCR = HQLA / Net Cash Outflows × 100`

### NSFR

1. Compute Available Stable Funding using funding-type ASF factors and maturity adjustments
2. Compute Required Stable Funding on loans, HQLA, and other assets
3. `NSFR = ASF / RSF × 100`

### Stress Testing

Scenarios apply shocks to HQLA values, deposit balances, and interest rates, then re-run LCR, NSFR, and funding gap calculations.

## Database ERD

```mermaid
erDiagram
    balance_sheet ||--o{ lcr_results : "date"
    liquidity_assets ||--o{ lcr_results : "date"
    cashflows ||--o{ lcr_results : "date"
    funding_sources ||--o{ nsfr_results : "feeds ASF"
    balance_sheet ||--o{ nsfr_results : "date"
    funding_sources ||--o{ funding_gap_results : "maturity"
    cashflows ||--o{ funding_gap_results : "date"

    balance_sheet {
        date date
        float total_assets
        float deposits
        float loans
        float capital
    }

    lcr_results {
        date date
        float hqla
        float net_cash_outflows
        float lcr
        string status
    }

    nsfr_results {
        date date
        float available_stable_funding
        float required_stable_funding
        float nsfr
        string status
    }

    stress_tests {
        string scenario
        float lcr
        float nsfr
        float funding_gap
        float capital_impact
    }
```

## Deployment

Single-command execution via `python main.py`. No external services required (SQLite embedded). Power BI Desktop imports CSV exports from `powerbi/`.

Optional Streamlit dashboard (`streamlit run src/streamlit_app.py`) provides interactive exploration without Power BI.
