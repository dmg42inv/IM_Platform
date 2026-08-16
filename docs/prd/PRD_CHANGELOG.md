# PRD Change Log

## 2026-08-15 - v1.4.5

- Added `generate-html-dashboard` CLI command: produces a single
  self-contained HTML file (`html_dashboard.py`) with KPI cards, sortable/
  filterable Positions and Returns tables, Top/Bottom TVPI and Fair Value
  charts (Chart.js via CDN), a Pipeline & Lifecycle view, and a Data Quality
  tab. No server or build step - opens directly in a browser via `file://`.
  Supports the same `--group-by entity_id|fund_vehicle_id` option as the
  other real-data commands, so multiple dashboard "views" can be generated
  side by side.

## 2026-08-15 - v1.4.4

- Closed all previously-flagged fund investment gaps: added "New Space
  Capital GP Com SCSp" (G42's carry vehicle, traced through its 2020 origin,
  2022 restructuring, and current 2023 LPA) and "MGX Group Holding 1 Ltd
  (GP)" (G42's funding of MGX's GP costs, a genuine 3rd MGX vehicle) to the
  structural register. Clarified that New Space Capital Fund I's ~20
  drawdown notices are sequential capital calls funding a single ICEYE
  position, not 20 separate deals - the Sub-Fund's own legal documents state
  it exists solely to hold that investment.
- Added a manually-sourced valuation for MGX I Denali Holding LP (the
  tracker's own NAV tab has no row for it) directly from its Q3 2025
  capital account statement, cross-checked against the tracker's dedicated
  "MGX" tab.
- Added the `generate-output-pack` CLI command, producing the full V1
  Output Pack per `V1_Output_Pack_Spec.md`: `Portfolio_Snapshot`,
  `Returns_Summary`, `Pipeline_and_Lifecycle` (new - lifecycle_state funnel
  counts/conversion rates), `Monitoring_Summary` and `Governance_and_Control`
  (placeholder tabs - no monthly monitoring or IC/governance decision input
  dataset exists yet, so these are explicitly marked "not available" rather
  than fabricated), `Data_Quality_Exceptions`, `Register_View_Used`, plus a
  Markdown summary note (`build_summary_note` in `output_pack.py`) covering
  headline numbers, TVPI movers, and data quality caveats.
- Added `ownership_pct_fully_diluted_latest` column to `Portfolio_Snapshot`
  per spec (currently always blank - no cap table snapshot adapter exists
  yet).

## 2026-08-15 - v1.4.3

- Built the V1 real-data pipeline (as opposed to the synthetic `run` demo path):
  `tracker_adapter.py` (extracts cashflow/valuation strictly from the tracker's
  `CF (Equity, Debt)`, `CF (Funds)`, and `NAV` tabs - all other tabs are
  downstream reports and out of scope), `document_intake.py` (builds the
  structural Investment Register ab initio from primary legal documents, with
  OCR fallback for scanned/image evidence), `entity_reconciliation.py` (maps
  free-text tracker names to register entity/fund/sub-vehicle ids, preserving
  prior confirmations across re-runs), and `register_views.py` (reusable
  rollup views over the register by `entity_id` or `fund_vehicle_id`).
- Adopted an explicit source-of-truth split: original transaction/legal
  documents are authoritative for structural facts (entities, instruments,
  commitments, lifecycle); the monthly tracker is authoritative for cash
  flow timing/amounts and valuations. Investment approval forms/summaries
  are explicitly NOT treated as primary sources.
- Added `build-real-output` CLI command producing `Portfolio_Snapshot` /
  `Returns_Summary` against real, document-verified data, with a
  `--group-by entity_id|fund_vehicle_id` option.
- Fixed a valuation rollup bug: when multiple tracker sub-vehicles (e.g. a
  fund's parallel vehicles) roll up to one parent entity, valuations must be
  summed across the latest mark per sub-vehicle, not collapsed to a single
  "latest row" post-remap (which silently discards all but one sub-vehicle's
  carrying value). See `build_subvehicle_parent_map` in `register_views.py`
  and the aggregation logic in `cli.py`'s `build-real-output` command.
- Deep-verified all 22 equity companies and 5 fund investments against
  primary legal documents (subscription/purchase agreements, capital call
  notices, capital account statements, side letters), correcting several
  items originally sourced from summary documents (e.g. AAICO/Applied AI's
  real $15M convertible note, InstaDeep's GBP contractual basis vs USD
  actual transfer, Cerebras warrants, ONT pre-emption tranche).
- Cross-verified fund investment cash flows/valuations line-by-line against
  the tracker's raw `CF (Funds)`/`NAV` rows; confirmed exact-match for New
  Space Capital Fund I, North Summit Capital Fund, Sinovation Disrupt Fund
  L.P., and Acies Investments Fund I L.P. Flagged remaining real gaps
  (New Space Capital GP Com SCSp entity not yet added; MGX HoldCo and MGX
  Denali (AIV) sub-vehicles pending further sourcing).

## 2026-08-13 - v1.4.0

- Consolidated recovered prior-draft context into the current PRD.
- Added Product Principles section.
- Added expanded canonical data and ontology baseline (entity, relationship, event, cash-flow, valuation, decision models).
- Added expanded reporting and KPI framework.
- Added governance, change, and release management details including environment control and traceability.
- Added indicative phase timeline/cadence.
- Added immediate decisions required and sign-off matrix.
- Added PRD completeness checklist artifact mapping recovered baseline sections to current PRD sections.

## 2026-08-13 - v1.4.1

- Added v1 implementation input data specification artifact.
- Added v1 output pack specification artifact.
- Added v1 intake checklist artifact for first ingestion run readiness.

## 2026-08-13 - v1.4.2

- Updated implementation specs to enforce USD as final reporting currency.
- Added explicit multi-currency handling requirements (GBP/EUR/USD/RMB and others) with FX-to-USD traceability fields.
- Added intake and validation checks for FX rate completeness and source tracking.

## 2026-08-13 - v1.3.0

- Added Target Operating Model and Ownership section with ownership model, governance cadence, RACI baseline, and operating acceptance criteria.
- Added Treasury and Fund Economics Requirements section covering treasury workflows, fee/carry logic, reporting controls, and acceptance criteria.
- Added Migration and Cutover Plan section covering migration waves, cutover controls, and acceptance criteria.

## 2026-08-13 - v1.2.0

- Added explicit business context for G42 Corporate, proprietary capital, and third-party capital raise strategy.
- Added explicit support for dual operating modes (as LP and as fund manager/GP).
- Expanded scope to include fund lifecycle workflows (capital calls, NAV support, LP reporting).
- Expanded instrument scope to equity, convertibles, derivatives/options, debt/loans, and fund investments.
- Added stakeholder requirement context for Board, CFO Office, Treasury, and Tax.
- Added workflow coverage map for deal, fund, instrument, governance, and risk lifecycles.
- Added recommended module-based build approach for phased implementation.
- Added explicit team requirement baseline section for Board, CFO Office, Treasury, Compliance, Risk, Tax, LP Relations, and Investment Team.
- Aligned PRD title version label with document control (v1.2).

## 2026-08-13 - v1.0.0

- Initial full PRD draft created with goals, scope, epic requirements, NFRs, phased plan, and risks.

## 2026-08-13 - v1.1.0

- Added explicit target direction for micro-services based architecture.
- Added agent intelligence requirements for file/investment change tracking and macro news monitoring.
- Added PRD governance model: semantic versioning, cadence, ownership, and sharing checkpoints.
- Added data and ontology strategy for transactional, analytical, and knowledge modeling needs.
- Added delivery readiness gaps and recommended workstreams.

## Versioning Rules

- Major (X.0.0): Material strategy/scope changes.
- Minor (1.X.0): New requirements or major section additions.
- Patch (1.1.X): Clarifications, wording improvements, typo fixes.
