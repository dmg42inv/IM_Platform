# PRD Change Log

## 2026-08-18 (afternoon/evening) - v1.10.0

- **Display/formatting rework, done structurally rather than case-by-case**:
  all dollar figures and multiples across the dashboard and its hover
  citations now format consistently (1 decimal by default, only stepping
  to 2 decimals when 1 would hide a genuinely non-zero small value), large
  exact dollar figures in citation text now render in millions instead of
  full unrounded numbers, multiples are capped for absurd values instead
  of showing a literal thousands-x figure, and Invested/Distributions
  hover text was simplified to a plain sourcing statement with an explicit
  "validated against a primary document" variant for positions specifically
  cross-checked.
- **Fixed a real IRR calculation bug**: the XIRR solver only used
  Newton-Raphson, which can fail to converge - and silently return a blank
  result - for extreme-loss cash flow shapes. Added a bisection fallback
  so a genuine large negative return now displays correctly instead of a
  blank cell.
- **Corrected several commitment-amount figures against primary/updated
  documents** (a formula-based cap superseded by the actual final signed
  subscription in one case; an instrument-level calculation slightly off a
  round headline figure due to per-unit price rounding in another; a
  fund's original subscription commitment substantially reduced by a
  later, separately executed side letter irrevocably waiving the
  uncalled balance in a third) - each case is a distinct pattern, not
  fixed by one blanket rule, and each is documented with its own citation.
- **New standing policy: for fund vehicles, a Capital Account Statement
  (or equivalent fund administrator statement) is primary for cumulative
  Invested/Distributions, overriding the tracker's own cash-flow-derived
  sum when they disagree** - implemented as a structural override
  mechanism, not a one-off fix, and reusable for any fund found to have
  the same issue going forward. Found via a case where the tracker's own
  fund cash flow tagging had inconsistent sign conventions across
  otherwise-identical transaction types, inflating both Invested and
  Distributions by the same amount while the net position matched the
  fund statement exactly - a strong, checkable validation signal before
  trusting this kind of override (verify the net ties out before
  applying it, not just the gross figures).
- **Standing documentation convention** (reaffirmed again this session):
  no deal names, companies, or figures in the PRD/changelog/architecture
  docs - approach and structure only; specifics live in repo memory.

## 2026-08-17/18 - v1.9.0

- **Closed out a class of stale lifecycle-status gaps**: the register's
  `lifecycle_state` field can lag behind the tracker's own Live/Exited
  classification for a position pending user confirmation before
  overwriting - the existing register-vs-tracker triangulation check was
  already correctly detecting these mismatches; the gap was in resolving
  them, not detecting them. Also closed a related pattern: a position's
  debt/loan tranche can exist in cash flow data with no corresponding
  register row at all - now added from primary signed loan documents when
  found, including confirming exact dissolution/wind-up dates from
  registrar filings where available.
- **Resolved an open item via newly available external evidence**: an
  internal communication plus a portfolio company's own audited public
  filing both independently corroborated a prior figure, closing out a
  discrepancy that had been flagged and left open pending confirmation
  rather than silently assumed either way.
- **Rolled multiple fund vehicles forward to their latest quarterly fund
  reporting** (Capital Account Statements/Limited Partner Statements):
  commitment and NAV figures updated per vehicle. Found and (with user
  direction) applied a real, material commitment-transfer event on one
  vehicle, sourced from the fund administrator's own statement footnote
  (not yet cross-checked against a signed transfer/assignment agreement -
  flagged as such). Where an interim cash movement wasn't labelled with
  which specific vehicle it belonged to, attributed it by triangulating
  each candidate vehicle's remaining unfunded-commitment capacity rather
  than guessing (documented as inferred, not source-confirmed).
- **Codified a fund NAV/commitment roll-forward methodology** for the gap
  between a fund's quarterly NAV mark and the platform's monthly reporting
  cadence: interim NAV = last quarter-end NAV + contributions - 
  distributions since quarter-end (a pure cash roll-forward, not a new
  appraisal), with cumulative paid-in capital increased by the same
  amount (see `/memories/repo/architecture-policy.md` for the full
  methodology and worked reasoning - deal-specific figures and citations
  live in repo memory, not here).
- **Fixed three real bugs found via this work**: (1) a cash flow sign-
  convention error - new capital-call rows entered with the wrong sign
  wrongly inflated Distributions and understated Invested (the pipeline
  buckets cash flow purely by amount sign, not by its label - confirmed
  by reading the recompute logic directly); (2) a fund vehicle with no
  line item in the tracker's own Live/Exited report tabs at all was
  silently absent from the dashboard's main deal table despite being
  fully tracked in the register/valuation extract - fixed by injecting a
  synthetic deal row for any such vehicle, still fully recomputed from the
  register/cashflow/valuation data, never hardcoded; (3) a dashboard CSS
  bug where a container's horizontal-scroll style was inadvertently
  clipping hover-tooltip popups (per the CSS overflow spec, one axis can't
  clip while the other stays fully visible) - fixed by isolating
  horizontal scroll to a dedicated wrapper around each table.
- **Standing documentation convention reaffirmed**: the PRD and changelog
  describe approach/methodology/structure only - portfolio-company names,
  deal figures, and citations belong in repo memory (or a dedicated
  source-of-truth log), never in these documents.

## 2026-08-16 - v1.8.0

- **Extended the Vintage and Commitment Verification Discipline** (PRD_v1.md
  section 19.5) with three more rules from today's closing round: a
  business decision (e.g. a confirmed commitment cancellation) can
  override a document-derived figure ahead of paperwork catching up, but
  must be labelled as pending its own document, not treated as equivalent
  to one; investor-relations pages and exchange/SEC filings are strong
  independent evidence for listed portfolio companies and should be
  checked proactively with a running log kept (see
  `data/source_of_truth/Listed_Entity_IR_Check_Log.md`); the challenge
  discipline applies to the user's own recollection just as much as to
  documents - a signed document beats an unconfirmed memory of a figure.
- **Applied user-confirmed business decisions**: Beyond Limits' undrawn
  ~$10M Series C tranche is cancelled (Committed pinned to Invested,
  pending a formal cancellation document); ONT's JV co-investment never
  materialized (same treatment).
- **Verified vTv Therapeutics via a public IR press release** (Nasdaq:
  VTVT) rather than only internal drafts - confirmed $25M/G42 Investments
  AI Holding RSC Ltd/close date, and corrected the FDA milestone figure
  to $30M (a draft 8-K redline had shown a superseded $20M).
- **Challenged two user recollections against signed documents**: Mena
  Mobile's Series B Purchase Agreement Schedule II explicitly states
  USD 8,000,000 (not AED, as recalled); vTv Therapeutics' signed
  documents/public filing show $25M with no support found for a
  recalled $15M/fee-refund figure - both kept at the document-verified
  amount, with the user's recollection logged as an open item rather
  than silently applied.
- **Flagged EsyaSoft's likely exit** (a $5,000,000 cash flow already on
  record, exactly 2x the $2.5M invested) as an open item pending further
  detail - lifecycle_state left unchanged until confirmed.

## 2026-08-16 - v1.7.0

- **Added a Vintage and Commitment Verification Discipline section**
  (PRD_v1.md section 19.5), codifying lessons from a full re-verification
  pass across the portfolio: always check all candidate dates (contract
  signing, stated closing date, actual cash movement, tracker's existing
  value) since they can genuinely diverge by months or years; a
  correct-looking figure is not evidence it was verified; exact cash-flow
  amount matches are the strongest confirmation; split positions (e.g. a
  financing round plus a related token/warrant leg) must be computed
  independently, not pooled; commitment figures can legitimately differ
  from a simple cash total in either direction (undrawn tranches,
  in-kind/cashback credits) but must be document-traceable either way; a
  negative Remaining Commitment is a signal to investigate, never to
  publish; every currency actually used must be accounted for, not
  silently dropped from a USD total.
- **Re-verified vintage/commitment figures against primary documents** for
  HeyGears, Beyond Limits, EsyaSoft, Flyr, Jysan Technologies, Liquid AI,
  School Hack, and ONT, applying the discipline above - each change is
  fully cited in the register (`confirmed_by`) rather than applied
  silently. Notably: Liquid AI's commitment is net of a $5.78M cashback
  credit due back from a G42-affiliated compute provider under a linked
  service order; School Hack's commitment includes a $250,000 compute
  credit alongside the cash equity subscription; ONT's Committed is set
  equal to Invested (zero Remaining Commitment) since a previously
  contemplated JV co-investment did not proceed.
- **Fixed two real bugs in citation-confidence scoring**
  (`register_citations.py` `short_citation()`): a citation already marked
  CONFIRMED/executed was being downgraded back to "unverified" purely
  because its text also mentioned "term sheet" or started with
  "AI-extracted" as historical context - both checks now respect the
  `verified` flag instead of overriding it unconditionally.
- **Fixed a double-counting bug** where one underlying position reported
  as more than one tracker line (e.g. a equity/token split, or a
  financing-round/warrant split) showed the same pooled Invested/
  Distributions/Committed on every line sharing that position - each line
  now computes from its own evidence, falling back to the pooled figure
  only when a line truly has no separately-tagged data.
- **Added a standing collaboration principle** (PRD_v1.md section 26): the
  platform (and any agent operating it) is expected to challenge an
  unverified claim rather than silently accept or silently override it -
  surface the evidence and let the accountable person decide, unless
  judgment has been explicitly delegated.
- **Dashboard usability**: Live Investments table columns are now a fixed,
  consistent width (via colgroup + table-layout: fixed) instead of
  reflowing per regeneration; added a curated "Notes" panel beneath the
  Live Investments table giving leadership-level context on figures that
  would otherwise look surprising (deal splits, vintage basis, commitment
  treatment) - written to illuminate status, not to flag corrections.

## 2026-08-16 - v1.6.0

- **Made change detection a mandatory, standing operating step** (PRD_v1.md
  section 19.4), not an occasional check: at the start of every session,
  and always before finalizing a month-end report, all four file-level
  outcomes must be positively confirmed - added, modified, deleted, and
  renamed/moved - not just "anything new". Closed a real gap in
  `scan_for_updates.py`: the manifest diff previously only detected
  added/modified files; deletions were silently absorbed into the new
  manifest with no flag, and a rename looked indistinguishable from a
  brand-new unrelated file. Added `deleted_files` (path present in the old
  manifest, missing from the new one) and `renamed_files` (a same-size
  heuristic pairing a deleted path with an added path - a heuristic, not
  proof, always confirm by opening the file) to `_diff_manifests()` /
  `_match_renames()` / `scan_for_new_investments()`, surfaced in both the
  CLI output and the dashboard's Data Quality scan section.
- **Physically separated durable source-of-truth artifacts from
  regenerable output** (PRD_v1.md section 19.4, `System_Architecture.md`
  section 4): `data/source_of_truth/` now holds the investment register,
  entity reconciliation mapping, change-detection manifest baseline, and
  frozen dated cash flow snapshots - files that must never be silently
  regenerated wholesale. `data/outputs/` holds only fully rebuildable
  reports (dashboards, output packs, preview/reconciled extracts, scan
  reports), safe to delete at any time. All default paths live in
  `cli.py`.

## 2026-08-16 - v1.5.0

- **Crystallized the source-of-truth architecture as durable policy**, not
  just implementation detail, after a full working session applying it in
  practice. Added PRD_v1.md section 19.4 ("Source-of-Truth Hierarchy") and
  two new Product Principles (section 26): primary documents over
  summaries always; every reported data point carries an honest confidence
  citation. Populated the previously-empty
  `docs/architecture/System_Architecture.md` with the actual as-built
  pipeline (Mermaid diagram, adapter responsibilities, key artifacts,
  derived-metric formulas, known limitations) - this is now the canonical
  technical reference, to be updated alongside code changes.
- **Corrected a real architectural inversion**: the tracker's own monthly
  report tabs ("1. Live" / "2. Exited") had been used as a data source for
  Committed/Invested/Remaining/Distributions/Carrying Value/Gain/TVPI. Per
  explicit user correction, those tabs are a *format* reference only - all
  derived metrics are now computed independently from the register
  (commitment) + cash flow extract (invested/distributions) + NAV extract
  (carrying value), matching the tracker's own underlying formula logic
  (verified directly against its `A. All deals (a)` tab) without depending
  on its derived output. See `V1_Input_Data_Spec.md` section 7.5.
- **Added a citation confidence taxonomy** (`V1_Input_Data_Spec.md` section
  7.4): every `confirmed_by` citation is now mechanically classified as
  either "verified" (signed/executed document, or explicitly tagged
  CONFIRMED) or "shallow" (an internal summary referencing a document that
  was never independently opened) - never blurred together. Caught and
  fixed two real gaps this way: "Endless (Matt Dalio) and E-line" had been
  merged from a non-binding term sheet read alone (the folder had 15+
  signed documents never opened) - split into 2 real entities (Endless
  Studios $8M, E-Line Ventures $6M) after reading the actual signed SPAs;
  TFH-Worldcoin's investing entity was unconfirmed - resolved to MOZN
  Holding RSC Ltd from the actual signed Side Letter/signature page.
- Added `entity_glossary.py` (clean display names for folder-derived
  entity_ids), `register_citations.py` (SPA/CAS-confirmed investing
  entity, commitment, instrument/series, and close-date citations, with
  the confidence taxonomy above), file-level change detection
  (`scan_for_updates.py` manifest diff with plain-English impact notes),
  and a frozen, dated `Cashflow_SourceOfTruth` snapshot mechanism so
  reporting doesn't silently drift as the live tracker file changes.
- Assessed feasibility of clicking a data point to open the exact cited
  document location: page-level deep-linking (`file:///doc.pdf#page=N`) is
  reliable and planned; exact-clause/sentence highlighting is feasible only
  for clean digital PDFs with an embedded text layer (not scanned/OCR'd
  PDFs or DOCX sources) - not to be oversold as a universal capability.

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
