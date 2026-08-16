# IM Platform Product Requirements Document (PRD) v1.8

## 1. Document Control

- Product: IM Platform
- Version: 1.8
- Date: 2026-08-16
- Status: Draft
- Owners: Product, Engineering, Operations

## 2. Purpose

Define the scope, requirements, and phased delivery plan for the IM Platform, enabling end-to-end institutional investment operations from sourcing and due diligence through monitoring, valuation, risk, compliance, and reporting.

### 2.1 Business Context

- Organization context: G42 Corporate investment management function.
- Capital model: Manage proprietary balance-sheet capital and third-party capital.
- Platform mandate: Support fund launch, operation, and scale as external capital formation grows.
- Investment strategy baseline: Start with PE/VC technology focus while remaining sector, geography, and stage agnostic over time.

## 3. Vision

Build a unified operating system for institutional investment teams that improves decision quality, execution speed, governance, and auditability across the full investment lifecycle.

## 4. Goals and Non-Goals

### Goals

- Provide a single source of truth across deal, position, and portfolio data.
- Standardize core investment workflows with role-based controls and approvals.
- Improve cycle times for due diligence, IC decisions, and periodic reporting.
- Strengthen compliance, traceability, and operational resilience.
- Support both LP and GP operating modes, including cases where the organization is an LP and cases where it manages third-party LP capital.
- Support multi-instrument investing across direct and indirect strategies.

### Non-Goals (v1)

- Retail investor onboarding and distribution workflows.
- High-frequency intraday trading and OMS/EMS replacement.
- Full accounting ledger replacement in v1.

## 5. Users and Stakeholders

- Investment Team: Analysts, Associates, VPs, Partners.
- Investment Committee: Decision makers and approvers.
- Board: Governance oversight, strategic review, and decision assurance.
- CFO Office: Performance views, lifecycle tracking, and governance transparency.
- Treasury: Liquidity, cash planning, capital deployment, and hedging visibility.
- Operations: Data stewards, portfolio operations.
- Risk and Compliance: Risk officers, compliance managers.
- Tax: Tax operations, structuring support, and reporting dependencies.
- Finance/Valuation: Controllers, valuation analysts.
- Leadership/LP Relations: Management, reporting consumers.

## 6. Problem Statement

Current investment processes are fragmented across spreadsheets, email, and disconnected tools, causing inconsistent data definitions, delayed approvals, limited transparency, and elevated operational and compliance risk.

## 7. Scope

### In Scope

- Identity and access management.
- Master data and taxonomy governance.
- Pipeline and stage-gate lifecycle management.
- Due diligence workspace and artifacts.
- Investment committee workflow and approvals.
- Position register and portfolio state tracking.
- Monitoring, valuation, risk, compliance, and reporting.
- Agent operations for workflow support and quality controls.
- Deal lifecycle coverage from sourcing through exit, including visited/dropped decisions and rationale.
- Fund lifecycle workflows including capital calls, NAV workflows, and LP reporting.
- Instrument lifecycle support for direct equity, convertibles, options/derivatives for hedging or exposure, loans/debt products, and fund investments.

### Out of Scope (for v1 delivery)

- Multi-jurisdiction tax engine automation.
- Real-time market data streaming architecture.
- End-customer mobile application.

## 8. Success Metrics

- 30% reduction in deal progression cycle time from intake to IC decision.
- 50% reduction in manual reconciliations between pipeline, positions, and reporting.
- 95% of required approvals captured in-system with complete audit trail.
- 99.9% monthly availability for business-critical workflows.
- 100% report lineage traceability for published portfolio reports.
- 100% board and CFO packs generated from governed platform data sources.
- 90%+ investment records carrying full lifecycle state, ownership, and status history.

## 9. Functional Requirements by Epic

### E1 Identity and Access

- Role-based access control with configurable permission sets.
- SSO integration and MFA enforcement.
- Segregation of duties for sensitive approvals.
- Session and access audit logs.

### E2 Master Data and Taxonomy

- Central entities for issuer, fund, security, counterparty, and taxonomy.
- Data stewardship workflows (create/update/deprecate).
- Validation rules, deduplication checks, and change history.
- Canonical instrument taxonomy spanning equity, convertibles, derivatives/options, debt/loan products, and fund interests.

### E3 Pipeline and Stage-Gates

- Deal pipeline with configurable stages and entry/exit criteria.
- Mandatory artifacts and quality checks per gate.
- Task orchestration, SLA tracking, and bottleneck visibility.
- Explicit tracking of sourced, visited, dropped, approved, live, partially exited, and fully exited states with reason codes.

### E4 DD Workspace

- Structured due diligence checklist templates.
- Artifact repository with versioning and tagging.
- Findings log with owners, severity, and remediation status.

### E5 IC Workflow

- IC memo creation, review, and approval routing.
- Voting and conditional approval handling.
- Decision records linked to assumptions and artifacts.

### E6 Position Register

- Canonical position register across active and exited positions.
- Ownership, exposure, and status tracking.
- Historical snapshots and adjustment audit trail.
- Performance tracking by instrument-appropriate metrics (for example: MOIC, IRR, TVPI, DPI, yield, mark-to-market where applicable).

### E7 Monitoring

- KPI and covenant monitoring framework.
- Exception alerts and escalation rules.
- Portfolio health dashboard with drill-down.
- Post-investment monitoring workflows linked to original underwriting assumptions.

### E8 Valuation

- Valuation model inputs, review workflow, and sign-off.
- Scenario and sensitivity analysis.
- Valuation history with rationale logging.

### E9 Risk

- Risk register with taxonomy and control mapping.
- Scoring, trend analysis, and concentration views.
- Mitigation task tracking and overdue alerts.

### E10 Compliance

- Policy rules engine for pre/post-trade checks where relevant.
- Breach capture, investigation, and disposition workflow.
- Regulatory evidence package and audit readiness support.
- Compliance and tax control checkpoints embedded in relevant workflows.

### E11 Reporting

- Standardized internal and LP reporting packs.
- Report templates with data lineage and approval status.
- Scheduled generation and distribution controls.
- Fund operations reporting support including capital call outputs, NAV support packs, and LP communication artifacts.

### 9.1 Workflow Coverage Map

- Deal lifecycle: Sourcing -> screening -> diligence -> IC -> execution -> monitoring -> partial/full exit.
- Fund lifecycle: Fund setup -> commitments -> capital calls -> deployment -> valuation/NAV support -> LP reporting.
- Instrument lifecycle: Security setup -> term capture -> booking -> valuation -> risk/compliance monitoring -> exit/closure.
- Governance lifecycle: IC approvals -> delegated approvals -> compliance checks -> audit trail and evidence retention.
- Risk lifecycle: Pre-investment underwriting -> post-investment monitoring -> mitigation -> escalation -> closure.

### E12 Agent Operations

- Agent-assisted drafting, validation, and workflow reminders.
- Human-in-the-loop checkpoints for critical actions.
- Prompt, output, and action logs for governance.
- Change intelligence agents to track file-level changes, investment state changes, and workflow transitions.
- Macro intelligence agents to ingest relevant market and policy news and map impacts to investments and risk themes.
- Configurable daily/weekly digests and threshold-based alerts for portfolio teams.

## 10. Non-Functional Requirements

- Security: Encryption at rest and in transit; least-privilege access.
- Reliability: 99.9% availability target for critical services.
- Performance: <2s median response for core list/detail pages.
- Scalability: Support growth in deals, entities, and report volume.
- Auditability: Immutable audit logs for key workflow actions.
- Observability: Metrics, logs, tracing, and SLA dashboards.

## 11. Dependencies and Integrations

- Identity Provider (SSO/MFA).
- Document storage and collaboration tooling.
- Data warehouse/lake for historical analytics.
- Optional downstream reporting and BI tools.
- Event bus/stream platform for cross-service event propagation.
- External news and macro data providers for intelligence workflows.
- Market/reference data providers and fund administrator interfaces where applicable.

## 12. Risks and Mitigations

- Data quality risk: Mitigate with stewardship workflows and validations.
- Change management risk: Mitigate with staged rollout and role-based training.
- Over-automation risk: Mitigate with human approvals for high-impact actions.
- Integration delays: Mitigate with phased dependency sequencing.

## 13. Phased Delivery Plan

### Phase 1: Institutional Core

- Epics: E1, E2, E3, E4, E5, E6.
- Outcome: Controlled deal-to-decision-to-position backbone.
- Architecture baseline: modular domain boundaries with service-ready APIs and canonical events.

### Phase 2: Fund and LP Operations

- Epics: E7, E8, E10, E11.
- Outcome: Standardized monitoring, valuation, compliance, and reporting.
- Agent baseline: operational change summaries and quality control assistants.

### Phase 3: Multi-Asset Expansion and Intelligence

- Epics: E9, E12 (+ cross-epic enhancements).
- Outcome: Advanced risk intelligence and agent-driven operating leverage.
- Platform evolution: progressively decomposed micro-services and expanded intelligence pipelines.

## 14. Acceptance Criteria (v1)

- All Phase 1 workflows are executable end-to-end in production.
- IC decisions and position creation are fully auditable.
- Baseline internal reporting pack generated from platform data.
- Access controls and compliance evidence validated by control owners.

## 15. Open Questions

- Which external systems are authoritative for security master at go-live?
- What is the minimum required LP report set for Phase 2 sign-off?
- Which risk models are mandatory in Phase 3 versus optional?

## 16. Cross-Phase Architecture and Platform Strategy

### 16.1 Target Architecture

- Target state is micro-services based architecture organized by business domains (identity, pipeline, DD, IC, positions, monitoring, valuation, risk, compliance, reporting, agent ops).
- Delivery starts with modular services and clear API/event contracts in early phases, with decomposition depth increased over time based on scale and team maturity.
- Service boundaries must preserve data ownership and reduce cross-domain coupling.

### 16.2 Platform Design Principles

- API-first design with versioned contracts.
- Event-driven integration for major state changes and audit events.
- Backward-compatible schema evolution and migration playbooks.
- Zero-trust security posture and policy-by-default access controls.

### 16.3 Operational Readiness

- Per-service SLOs, observability, and on-call ownership.
- Runbooks for incident response, failover, and recovery.
- Progressive delivery controls (feature flags, canary releases where applicable).

## 17. Agent Intelligence and Change Tracking Strategy

### 17.1 Change Tracking Scope

- Track document and file changes across core investment artifacts.
- Track investment lifecycle changes (stage movement, assumptions, valuation updates, risk/compliance status changes).
- Track user action trails for explainability and governance.

### 17.2 Macro and External Intelligence

- Ingest macroeconomic, sector, policy/regulatory, and issuer-relevant news feeds.
- Entity-link external signals to internal portfolio entities and themes.
- Generate explainable impact summaries with source references and confidence levels.

### 17.3 Guardrails

- Human approval required for any recommendation that changes investment state.
- All agent outputs must be auditable and reproducible.
- Escalation and suppression controls to prevent alert fatigue.

## 18. PRD Governance, Versioning, and Shareability

### 18.1 Versioning Model

- Semantic PRD versioning: major.minor.patch.
- Major for material scope/strategy changes; minor for new requirements; patch for clarifications.

### 18.2 Change Management

- Maintain a dated change log and decision log in the PRD directory.
- Monthly review cadence with ad hoc updates for critical requirements changes.
- Explicit owners for approving scope, architecture, and compliance-impacting changes.

### 18.3 Shareability

- Maintain a stakeholder-friendly summary companion document for leadership and non-technical audiences.
- Publish controlled snapshots for review milestones (phase gates, architecture review, compliance review).

## 19. Data and Ontology Strategy

### 19.1 Data Stores and Usage

- Use relational stores for transactional integrity and workflow state.
- Use analytical stores for portfolio analytics, trends, and reporting workloads.
- Use document/object storage for DD artifacts and evidence packs.

### 19.2 Ontology and Knowledge Modeling

- Maintain an investment ontology for entities, relationships, events, and controls.
- Define canonical business terms and mappings to physical schemas.
- Apply ontology-informed validations to improve consistency across workflows and reporting.

### 19.3 Data Governance

- Data quality scorecards, lineage, and stewardship accountability by domain.
- Policy-based retention and legal hold controls where required.
- Periodic taxonomy and ontology review as product scope expands.

### 19.4 Source-of-Truth Hierarchy (V1, as implemented)

Established through direct experience building the V1 real-data pipeline
(2026-08-15/16). This is a durable policy, not an implementation detail -
any future rebuild (platform, agent, or manual process) must preserve it.

- **Original transaction/legal documents are primary** for structural facts:
  legal entity name, investing entity/vehicle, instrument/series, initial
  commitment amount, close date, lifecycle state. Internal summaries
  (Investment Approval Forms, Investment Summaries, non-binding term
  sheets) are NOT primary sources - they may point to the right document,
  but the signed/executed document itself must be read and cited.
- **The monthly Treasury tracker is primary only for cash flow timing/
  amounts (what was actually transferred) and NAV/valuation marks** - not
  for structural facts, and not for derived metrics. The tracker itself is
  a manual Excel-based process the platform is meant to reduce dependency
  on over time, not encode as ground truth.
- **Derived metrics (Remaining, Gain, TVPI, IRR) must be computed from
  primary sources by explicit formula**, not copied from the tracker's own
  report views - even when a tracker report (e.g. a monthly Live/Exited
  pack) is used as a *formatting/structure* reference. Verify formula
  parity against the tracker's own underlying calculation only as a
  cross-check, never as the source.
- **Every citation must state its confidence honestly**: a clear line
  between "confirmed from a signed/executed document" and "referenced in
  an internal summary, not yet independently verified" - never presented
  as equivalent. A citation that says a signed document is needed but
  hasn't been read yet is a flag to go read it, not a permanent caveat.
- **The structural register (investment register + entity reconciliation)
  is the durable middle-layer database**: built once from primary
  documents, reused by every downstream report. It is not re-derived by
  re-reading raw files on each run. Cash flow/valuation extracts pulled
  from the tracker should be frozen as dated, point-in-time snapshots
  (decoupled from whatever the "current" tracker file happens to be) so
  reporting doesn't silently drift as the tracker is updated at the source.
- **Display names are governed separately from internal identifiers**:
  internal keys may be derived from document-folder names for stability,
  but anything shown to a reader must be the real/clean name, with a
  glossary mapping and legal-name reference where the two differ.
- **Change detection is a required, standing operating step, not an
  afterthought or an occasional check**: at the start of every working
  session, and always before finalizing a month-end report, the platform
  must diff the current source document folders against a stored baseline
  manifest and positively confirm all four outcomes for every file -
  **added, modified (content changed), deleted, and renamed/moved** - each
  flagged with a plain-English note on what part of the report it likely
  affects. A scan that only checks for additions is not sufficient: a
  deleted or renamed primary document (e.g. a superseded SPA, a corrected
  capital account statement) is exactly the kind of change that must not
  be missed silently. Renamed/moved detection is a same-size heuristic
  pairing a disappearance with an appearance - not proof, and must be
  confirmed by opening the file, but is far better than no signal at all.
  This check governs whether "all is saved and captured well" before a
  report is treated as final.
- **Durable artifacts are physically separated from regenerable output**:
  the register, entity-reconciliation mapping, change-detection baseline,
  and any frozen point-in-time extract live in a distinct location from
  disposable, fully-rebuildable reports (dashboards, output packs,
  preview extracts) - so it is structurally obvious what must never be
  silently overwritten versus what is safe to delete and regenerate at
  any time.

### 19.5 Vintage and Commitment Verification Discipline (added 2026-08-16)

Learned through a full working pass re-verifying vintage years and
commitment amounts across the portfolio against primary documents. These
are durable verification rules, not one-off fixes:

- **A date or amount that "looks right" is not evidence it was verified**:
  always independently confirm close date, investing entity, instrument,
  and commitment amount together from the same primary document - a
  citation can coincidentally show the correct year while still being
  wrong on amount or entity.
- **Vintage/closing has three or four candidate dates that can genuinely
  diverge by months or years - check all of them**: (1) the contract/SPA
  signing date, (2) a separately-stated Closing Date if a closing binder
  exists, (3) the actual cash movement date in the cash flow ledger (the
  most concrete evidence of when capital was actually deployed), and (4)
  the tracker's own existing value as a cheap sanity signal. When a deal
  spans two calendar years (e.g. an early convertible note that converts
  a year later), vintage uses the earliest first-capital-deployment date.
- **Exact-amount cross-checks against realized cash flow are the strongest
  confirmation available** (e.g. a register figure matching an actual
  cash movement to the cent) - prioritize this over any narrative summary,
  however confident-sounding.
- **When one underlying position is split across more than one
  reporting line** (e.g. a financing round and a related token/warrant
  leg, or an original round and a later add-on tranche), each line's
  Committed/Invested/Distributions must be computed from that line's own
  evidence, not pooled from the whole position - otherwise the same
  capital or return gets counted twice across rows.
- **A commitment figure can legitimately differ from a simple cash total**
  in either direction, and both must be traceable to a document, not
  assumed: (a) undrawn/unfunded tranches remain part of Committed even
  though not yet paid; (b) in-kind credits or cashback arrangements tied
  to a transaction (e.g. a compute/cloud-services credit, or a portion of
  proceeds contractually returned to an affiliated service provider) can
  net against or add to the headline commitment - go to the actual
  transaction documents to find these, don't infer them from the total
  alone.
- **A cross-check that produces a negative "Remaining Commitment" is a
  signal to investigate, not a number to publish as-is** - by definition,
  Remaining cannot be negative; either the commitment figure is
  incomplete/miscounted, or (as confirmed case-by-case with the business)
  a previously-contemplated additional commitment never materialized and
  should no longer be counted.
- **Every currency actually used must be accounted for** - silently
  excluding a non-USD-denominated commitment from a USD total (for lack of
  a captured FX rate) understates the figure; if a reliable conversion
  isn't available, flag the exclusion explicitly rather than presenting an
  incomplete total as if it were whole.
- **A business decision can legitimately override a document-derived
  figure ahead of paperwork catching up** - e.g. a commitment the business
  confirms it no longer intends to fund, even before a formal
  cancellation/amendment letter exists. Apply the business's confirmed
  position immediately, but record it explicitly as pending its own
  supporting document, and revisit once that document is obtained -
  never let a verbal/business confirmation quietly become "as good as
  a document" without being labelled as such.
- **For publicly listed portfolio companies, investor-relations pages,
  press releases, and exchange/SEC filings are strong independent
  evidence** - equal to or better than an internal transaction document,
  since public companies are legally required to disclose accurately.
  Check these proactively, not only when prompted, and keep a running log
  of what was checked and found (which entity, which source, what it
  showed) so the same lookup isn't silently repeated or lost.
- **The challenge discipline is not just about verifying documents - it
  applies to accepting user recollection too**: when the user's own
  stated memory of a fact (an amount, a currency, a figure) is checked
  against a signed document and the document says something else, say so
  plainly and keep the document's figure, rather than adopting the
  recollection because it was more recently stated. Do not fix what
  isn't broken by matching a claim that lacks evidence.

## 20. Delivery Readiness Gaps and Additions

The following workstreams should be established early to reduce delivery risk:

- Product operating model: Define RACI, decision rights, and cross-functional governance forum.
- Migration strategy: Plan spreadsheet/tool migration waves and cutover criteria.
- Test strategy: Define unit, integration, workflow, and controls-validation test layers.
- Security and compliance design: Add threat modeling, control mapping, and evidence automation plan.
- Reliability engineering: Define SLOs/SLIs, disaster recovery objectives, and incident processes.
- Change adoption: Training plan, role-based onboarding, and success measurement by team.
- FinOps and cost controls: Service-level cost observability and budget guardrails.

## 21. Recommended Build Approach

- Start with a capability map and domain boundaries that match the epics, then define API/event contracts before implementation.
- Deliver thin vertical slices first (for example: sourcing to IC for one instrument type) before broad horizontal expansion.
- Prioritize workflow backbone modules first: identity, master data, pipeline, DD, IC, position register.
- Add fund operations modules next: capital calls, valuation/NAV support, LP reporting, compliance evidence.
- Expand instrument coverage iteratively: equity first, then convertibles/debt, then derivatives and fund-of-fund patterns.
- Stand up shared platform foundations early: observability, audit logging, access governance, and integration framework.
- Use a gated operating cadence: product review, architecture review, controls review at each phase gate.

## 22. Team Requirement Baseline

- Board: Periodic board packs, investment concentration views, governance status, and approval lineage.
- CFO Office: Fund and portfolio performance, lifecycle status across investments, valuation movements, and governance dashboards.
- Treasury: Cash forecasting, capital call schedules, deployment pace, funding obligations, and hedging/exposure views.
- Compliance: Policy checks, breach workflows, exception approvals, and auditable evidence retrieval.
- Risk: Underwriting risk capture, ongoing risk score changes, concentration analysis, and mitigation tracking.
- Tax: Tax-relevant investment attributes, entity/jurisdiction classification, and reporting support data extracts.
- LP Relations: Investor-ready reporting packs, communication logs, and disclosure consistency controls.
- Investment Team: Deal pipeline state, diligence artifacts, IC decisions, position performance, and exit tracking.

## 23. Target Operating Model and Ownership

### 23.1 Product and Domain Ownership

- Define a domain owner for each major module: identity, master data, pipeline, DD, IC, positions, monitoring, valuation, risk, compliance, reporting, and agent operations.
- Define accountable business owner and accountable engineering owner per domain.
- Maintain a single decision register for scope, architecture, and controls-impacting decisions.

### 23.2 Governance Cadence

- Weekly product governance forum for priorities, dependency decisions, and escalation handling.
- Fortnightly architecture and integration review for API/event contract changes.
- Monthly controls and compliance review for policy effectiveness and evidence readiness.

### 23.3 RACI Baseline

- Product Management: Responsible for requirements and prioritization.
- Engineering: Responsible for delivery, reliability, and technical quality.
- Investment Operations: Responsible for workflow correctness and data stewardship execution.
- Risk and Compliance: Accountable for control definition and approval of control changes.
- Finance/Treasury/Tax: Consulted for lifecycle economics, liquidity, and reporting impacts.
- Board/Leadership: Informed through periodic governance and performance packs.

### 23.4 Operating Acceptance Criteria

- Every module has named business and engineering owners before phase entry.
- Every release has documented approval path, rollback owner, and incident contact.
- Governance forums produce actionable decisions with owners and due dates.

## 24. Treasury and Fund Economics Requirements

### 24.1 Treasury Workflows

- Cash forecasting by fund, strategy, and investment lifecycle stage.
- Capital deployment tracker versus commitments and liquidity limits.
- Capital call forecasting and payment obligation calendar.
- FX and hedging exposure views with approval and exception workflow.

### 24.2 Fund Economics and Fee Logic

- Management fee model support with configurable rates, periods, and bases.
- Carry/waterfall support requirements capture with calculation traceability.
- Expense allocation tracking with policy mapping and auditability.
- Validation workflow for fee and allocation outputs before reporting publication.

### 24.3 Reporting and Controls

- Treasury dashboard for liquidity runway, obligations due, and stress scenarios.
- Fund economics dashboard for fees, carry accrual trend, and variance analysis.
- Full lineage from source data to published treasury and economics reports.

### 24.4 Acceptance Criteria

- Capital call calendar and obligations are available with role-based access.
- Fee and allocation outputs are reproducible and independently reviewable.
- Treasury and fund economics packs are generated from governed platform data.

## 25. Migration and Cutover Plan

### 25.1 Migration Principles

- Migrate in controlled waves by module and team, not as a single big-bang event.
- Keep source-of-truth ownership explicit during each transition stage.
- Preserve audit trail continuity between legacy artifacts and new system records.

### 25.2 Migration Waves

- Wave 1: Identity, master data, pipeline, and DD artifacts.
- Wave 2: IC workflow, position register, and monitoring baseline.
- Wave 3: Treasury/fund economics outputs, compliance evidence, and reporting packs.

### 25.3 Cutover Controls

- Dual-run period for critical outputs (for example: selected reports and approvals).
- Reconciliation checkpoints with tolerance thresholds and remediation owners.
- Go/no-go gate with business, engineering, and controls sign-off.
- Rollback plan with clear triggers, owner, and communication protocol.

### 25.4 Acceptance Criteria

- Each wave has completed reconciliation sign-off before legacy decommission steps.
- No critical report/control process depends on unmanaged spreadsheet-only steps post-cutover.
- Post-cutover hypercare metrics are tracked and reviewed for at least one full reporting cycle.

## 26. Product Principles

- Workflow-first, not dashboard-first.
- Control-by-design, not control-after-the-fact.
- Canonical data model across all modules.
- Role-based and least-privilege access by default.
- Every material action is auditable.
- Configurable for new funds and instruments without rebuilding core logic.
- Primary documents over summaries, always - manual trackers and internal
  memos are useful fallbacks, never the source of record (see section 19.4).
- Every reported data point carries a citation with an honest confidence
  level - unverified is stated as unverified, not implied as confirmed.
- The platform (and any agent operating it) challenges an unverified claim
  rather than quietly accepting or quietly overriding it - surface the
  supporting or conflicting evidence and let the accountable person decide,
  unless they have explicitly delegated that judgment call.

## 27. Canonical Data and Ontology Baseline (Expanded)

The following baseline must exist from Phase 1 and evolve through Phase 3:

- Entity taxonomy: legal entity, fund, sub-fund, SPV, portfolio company, GP/LP, counterparty, instrument, valuation event.
- Relationship model: ownership and control paths across funds, SPVs, and underlyings, including rights and obligations.
- Event model: sourced, screened, approved, signed, funded, marked, distributed, exited.
- Cash-flow model: amount, currency, entity, instrument, purpose, date, and approval lineage.
- Valuation model: method, assumptions, confidence, reviewer, approver, and effective date.
- Decision model: decision body, vote, conditions, exceptions, rationale, and supporting evidence.

## 28. Reporting and KPI Framework (Expanded)

- Portfolio performance KPIs: IRR, TVPI, DPI, MOIC.
- Activity KPIs: deal throughput, conversion rates, and time-to-decision.
- Risk KPIs: concentration, covenant breach counts, and watchlist movement.
- Control KPIs: policy exceptions, approval SLA adherence, unresolved audit items.
- LP KPIs: report timeliness, query resolution time, distribution accuracy.
- Data KPIs: completeness, freshness, and reconciliation break rate.

## 29. Governance, Change, and Release Management

- Product Steering Committee including Investment, Risk, Compliance, Finance, Investor Relations, and Technology.
- Quarterly release planning with phase-gate approvals.
- Change control requiring versioned and approved workflow/data-model changes.
- Environment controls across development, UAT, and production with governed promotions.
- Full traceability from requirement to user story to test evidence to release.

## 30. Timeline and Delivery Cadence (Indicative)

- Phase 1 target: 12 to 16 weeks.
- Phase 2 target: 12 to 20 weeks.
- Phase 3 target: 16+ weeks as rolling expansion.

## 31. Immediate Decisions and Sign-Off Model

### 31.1 Immediate Decisions Required

- Preferred hosting pattern and data residency constraints.
- Phase 1 pilot boundaries (funds, strategies, and users).
- Named owners for data stewardship and workflow approvals.
- Compliance baseline by jurisdiction.
- Integration priority order (document system, accounting, KYC/sanctions provider).

### 31.2 Sign-Off Matrix

- To be finalized.
