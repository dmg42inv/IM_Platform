# V1 Intake Checklist

Date: 2026-08-13
Purpose: Operational checklist before first ingestion run.

## A. Access and File Readiness

- Confirm read access to investment documents root.
- Confirm read access to monthly monitoring root.
- Confirm latest monthly cut folder and as-of date.
- Confirm naming convention for source files or provide mapping.

## B. Mandatory Tables Received

- Master Entity file
- Investment Register file
- Transaction Cash Flow file
- Latest Valuation Marks file
- Monthly Monitoring file
- IC/Governance Decisions file

## C. Data Conventions Confirmed

- Date format is YYYY-MM-DD.
- Currency is ISO 4217.
- Final reporting currency is confirmed as USD.
- Cash flow signs are consistent (outflow negative, inflow positive).
- Lifecycle states use agreed values.
- Non-USD records include fx_to_usd, fx_rate_date, and fx_rate_source.

## D. Validation Complete

- Primary key uniqueness verified.
- Foreign key links validated.
- Missing required field report generated.
- Sample tie-out done on 3-5 investments.

## E. First Output Approval Gate

- As-of date approved.
- Reporting currency approved as USD.
- Metric definitions approved (IRR/MOIC/TVPI/DPI).
- Known caveats acknowledged.
- Go decision for first output pack.
