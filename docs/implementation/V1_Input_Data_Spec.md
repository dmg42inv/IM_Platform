# V1 Input Data Specification

Date: 2026-08-13
Version: 1.1
Purpose: Define the minimum required input data to produce a governed portfolio register, returns summary, and monthly monitoring output.

## Reporting Currency Policy (V1)

- Final reporting currency for all assembled outputs is USD.
- Source records may remain in local currencies (for example GBP, EUR, USD, RMB).
- Every non-USD monetary record must carry an FX rate to USD at record date.

## 1. Source Folders

- Investment documents root: C:\Users\divyesh.mahajan\OneDrive - G42\Desktop\0.1 SPPM ###\1. I N V E S T M E N T S  -  Global (Ex China)
- Monthly monitoring root: C:\Users\divyesh.mahajan\OneDrive - G42\Desktop\0.2 Portfolio Management - Monthly\1. Main (monthly report)

## 2. V1 Datasets and Required Fields

### 2.1 Master Entity File

Required columns:
- entity_id (string, unique)
- entity_name (string)
- entity_type (Fund, SPV, PortfolioCompany, Counterparty)
- parent_entity_id (string, nullable)
- strategy (string)
- sector (string)
- geography (string)
- currency_base (ISO code)
- status (Active, Inactive)

### 2.2 Investment Register File

Required columns:
- investment_id (string, unique)
- entity_id (string, links to portfolio company)
- fund_vehicle_id (string, fund/SPV making the investment)
- instrument_type (Equity, Convertible, Debt, Option, FundInterest)
- stage (Seed, SeriesA, etc.; optional if not applicable)
- initial_commitment_amount (number)
- investment_currency (ISO code)
- close_date (date)
- lifecycle_state (Sourced, Approved, Live, PartiallyExited, Exited, Dropped)
- lifecycle_state_date (date)

### 2.3 Transaction Cash Flow File

Required columns:
- cashflow_id (string, unique)
- investment_id (string)
- flow_date (date)
- flow_type (CapitalCall, Deployment, FollowOn, Distribution, Fee, Expense)
- amount (signed number; outflow negative, inflow positive)
- currency (ISO code)
- fx_to_usd (number; nullable when currency is USD)
- fx_rate_date (date)
- fx_rate_source (string)
- source_reference (document/file reference)
- approval_status (Draft, Approved)

### 2.4 Valuation Marks File

Required columns:
- valuation_id (string, unique)
- investment_id (string)
- valuation_date (date)
- fair_value_local (number)
- valuation_currency (ISO code)
- fx_to_usd (number)
- fx_rate_date (date)
- fx_rate_source (string)
- valuation_method (Market, Comparable, DCF, LastRound, NAVLookThrough)
- assumption_note (text)
- reviewer (string)
- approver (string)
- valuation_status (Draft, Reviewed, Approved)

### 2.5 Cap Table Snapshot File

Required columns:
- captable_snapshot_id (string, unique)
- investment_id (string)
- snapshot_date (date)
- security_class (string)
- shares_or_units (number)
- ownership_pct_fully_diluted (number)
- conversion_terms (text, nullable)
- liquidation_preference (text, nullable)

### 2.6 Monthly Monitoring File

Required columns:
- monitoring_id (string, unique)
- investment_id (string)
- as_of_date (date)
- revenue (number, nullable)
- ebitda (number, nullable)
- runway_months (number, nullable)
- covenant_status (Green, Amber, Red, NA)
- milestone_status (OnTrack, AtRisk, OffTrack)
- watchlist_flag (Yes, No)
- commentary (text)

### 2.7 Governance and IC Decisions File

Required columns:
- decision_id (string, unique)
- investment_id (string)
- decision_date (date)
- decision_body (IC, Delegated)
- decision_outcome (Approved, ApprovedWithConditions, Deferred, Rejected)
- conditions_text (text, nullable)
- rationale_summary (text)
- evidence_link (string)

## 3. Supported V1 Formats

- Preferred: CSV or XLSX tables with stable headers.
- Documents: PDF, DOCX for reference/evidence linking.
- Date format: YYYY-MM-DD.
- Currency codes: ISO 4217.
- Reporting currency: USD.

## 4. Data Quality Rules (V1)

- No duplicate primary keys per file.
- All foreign keys must resolve (investment_id, entity_id).
- No blank required fields.
- cashflow amount sign convention must be consistent.
- valuation_date cannot be earlier than close_date for the same investment.
- For non-USD records, fx_to_usd and fx_rate_date must be present.

## 5. Minimum V1 Cut Criteria

To produce first output pack, at least these must be available:
- Investment Register
- Transaction Cash Flow
- Latest Valuation Marks
- Monthly Monitoring (latest month)
- IC/Governance Decisions (for live positions)

## 6. Known Gaps Handling

- Missing fields are tagged as Unknown and surfaced in a data-quality exceptions sheet.
- Conflicting values are resolved using source priority and owner confirmation.
- Unmapped entities are parked in an entity-resolution queue.
