# V1 Output Pack Specification

Date: 2026-08-13
Version: 1.1
Purpose: Define the first reporting output generated from initial ingestion.

## Reporting Currency Policy (V1)

- All assembled output metrics are presented in USD.
- Local-currency source values are preserved for traceability where relevant.

## 1. Output Package

V1 output is delivered as:
- 1 portfolio workbook (XLSX)
- 1 summary note (Markdown/PDF)
- 1 data quality exceptions sheet

## 2. Workbook Tabs and Definitions

### 2.1 Portfolio_Snapshot

Columns:
- investment_id
- company_name
- fund_vehicle
- instrument_type
- lifecycle_state
- close_date
- invested_cost_local
- invested_cost_currency
- invested_cost_base
- latest_fair_value_local
- latest_fair_value_currency
- latest_fair_value_base
- unrealized_gain_loss_base
- ownership_pct_fully_diluted_latest
- watchlist_flag

### 2.2 Returns_Summary

Metrics by investment and aggregated by fund/strategy:
- PaidIn (sum of outflows)
- Distributed (sum of inflows excluding unrealized)
- ResidualValue (latest fair value)
- TVPI = (Distributed + ResidualValue) / PaidIn
- DPI = Distributed / PaidIn
- MOIC = (Distributed + ResidualValue) / PaidIn
- IRR (since inception; based on cash flow timing)

### 2.3 Pipeline_and_Lifecycle

- sourced_count
- dropped_count
- approved_count
- live_count
- partially_exited_count
- exited_count
- stage_conversion_rates
- median_time_to_decision_days

### 2.4 Monitoring_Summary

- as_of_date
- KPI trend flags
- covenant status distribution
- milestone status distribution
- watchlist movement month-over-month
- top exceptions with owner

### 2.5 Governance_and_Control

- IC decisions by outcome
- open conditions aging
- compliance/risk exception counts
- approval SLA breaches
- audit trail completeness percentage

### 2.6 Data_Quality_Exceptions

- dataset_name
- record_key
- issue_type
- issue_description
- severity
- owner
- remediation_due_date
- status

## 3. Summary Note Structure

Sections:
1. As-of date and data cut timestamp
2. Portfolio headline numbers
3. Returns highlights and notable movers
4. Risk and monitoring exceptions
5. Governance/control exceptions
6. Data quality caveats
7. Recommended actions before next cycle

## 4. Calculation Rules (V1)

- Reporting currency is fixed as USD.
- FX conversion uses provided fx_to_usd per record date.
- PaidIn includes all capital outflows, excluding management fees only if flagged separately.
- Distributed includes realized cash inflows.
- IRR uses dated cash flows and latest residual value as terminal value at as_of_date.

## 4.1 FX Audit Columns (Required in Supporting Output)

- source_currency
- amount_local
- fx_to_usd
- fx_rate_date
- fx_rate_source
- amount_usd

## 5. Delivery Cadence

- Initial backfill run: one-time for historical baseline.
- Recurring run: monthly.
- Recompute trigger: whenever valuation or cash flow restatement is posted.

## 6. Acceptance Check for V1 Output

- 100% live investments appear in Portfolio_Snapshot.
- Returns_Summary tie-out to underlying cash flows and latest marks.
- Monitoring_Summary aligns with latest monthly tracker cut.
- Data_Quality_Exceptions published with each run.
