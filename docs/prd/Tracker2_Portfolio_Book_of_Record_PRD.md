# Tracker 2 — Product Requirements & Build Charter
### Internal codename: **Tracker 2** · Candidate display title: **Portfolio Book of Record**

_Author: IM Platform build session · Date: 2026-08-24 · Status: DRAFT for sign-off_
_Companion docs: `docs/planning/Accounts_Team_Parity_Plan.md` (view inventory),
`docs/implementation/Dashboard_Style_Guide.md` (house style), `docs/prd/PRD_v1.md`._

---

## 1. Purpose & mandate
Senior management requires a portfolio dashboard that reproduces **substantially all** of the
accounts team's dashboard (`Accounts Team, G42_Investment_Portfolio_Dashboard_v2.3_21082026.html`,
"the Pack") — its layouts and views — **rebuilt on our own data** and in **our house style**.
Default disposition is **KEEP everything**; the user marks anything to drop, and adds where we
can go further. The user's own analytics (Tracker 1) will then be folded in additively.

**Success = a reviewer cannot point to a view in the Pack that Tracker 2 lacks, and every figure
Tracker 2 shows is grounded in our data or explicitly marked pending — never fabricated.**

## 2. Naming
- **Tracker 2** — internal codename only (never shown on screen; "tracker" was purged from UI copy).
- Display title: **Portfolio Book of Record** (final title subject to user confirmation).

## 3. Guiding principles (non-negotiable)
1. **Grounded in truth.** Every number traces to our source data with a citation; anything we
   cannot source is shown as **pending**, not estimated or blank-with-a-guess.
2. **House style = Tracker 1 personality.** Per `Dashboard_Style_Guide.md`: cream+green light
   theme (with dark toggle), EB Garamond, 3D bordered section boxes, green pill tabs,
   entity-scope tabs beside the page title, centre-aligned tables, formatted `$` tooltips,
   IB/SEC tone, the word "tracker" never in on-screen copy.
3. **One valuation basis.** The whole dashboard triangulates to a single, declared basis
   (see §6). No view may contradict another.
4. **No silent divergence.** Where the Pack's number rests on a definition we don't share, we
   reconcile or footnote — we never quietly show a different number under the same label.
5. **Additive, not destructive.** Tracker 1 stays intact; Tracker 2 reuses its engine.

## 4. Scope — views to deliver
Reproduce the Pack's **persistent entity-scope selector** (Consolidated / G42 / MGX / MOZN) and
its **nine views**, PLUS fold in Tracker 1's operational "Portfolio" view:

| # | View (from the Pack) | Default |
|---|---|---|
| 1 | Executive Overview (KPIs, since-inception, reconciliation, composition, ten-largest, concentration, observations) | Keep |
| 2 | **Investment Register** — one advanced fact-sheet per holding (see §5) | Keep — **depth upgrade** |
| 3 | Value Creation (KPIs, deployed vs FV, who created/lost, YoY, waterfall on two bases) | Keep |
| 4 | Portfolio Evolution (since inception, opened/closed per year, as-at any date) | Keep |
| 5 | Geography (country, region, region × sector) | Keep |
| 6 | Sector (sector & sub-sector, growth over time, contribution to value) | Keep |
| 7 | Concentration Risk (5-measure score, curve, single-name dependency, by dimension) | Keep |
| 8 | IFRS & Audit Trail (classification schedule, valuation method, reconciliations, basis of prep, audit log) | Keep — **data gap, see §7** |
| 9 | Change Log (open items, version history) | Keep |
| 10 | **Portfolio (operational)** — Tracker 1's embedded Live/Exited/Vintage/NAV/All-Cashflows/Ownership/Log/Monthly-Diff/Glossary, cited to source cell | **Add (from Tracker 1)** |

## 5. The Investment Register depth upgrade (explicit user note)
The Pack's register is **substantially more advanced** than Tracker 1's. Tracker 2's per-holding
fact sheet must reach the Pack's depth, field-by-field:
- **Identity & provenance** — legal entity, sector, jurisdiction/domicile, instrument, ownership %,
  "where it comes from" (source workbook cell).
- **Measurement at reporting date** — IFRS classification (FVOCI/FVTPL/…), valuation method,
  fair value, cost, value created, multiple, weight, independently-valued flag.
- **Value-creation timeline** (per holding).
- **Movement summary** and **movement by reporting period** on **two bases** (YTD from 1 Jan;
  since inception from first recognition), each with a bridge.
- **Cash movements on record**, each cited to its source cell.

Every field above gets a row in the **Metric Dictionary** (§8) with definition, formula, source,
and — critically — a **have / derive / need-data** status, so gaps are visible before we build.

## 6. Data foundation & the valuation-basis reconciliation (blocker to resolve first)
We already found Tracker 1's two internal views disagree on the same book:
- Overview / `portfolio.sqlite` → **Live report-tab** basis (FV 3,735.4m, invested 1,903.4m).
- Embedded Portfolio dashboard → **NAV-tab + fund CAS** basis (FV 4,568.3m, invested 2,160.2m).

**Requirement R-1:** before building Tracker 2 views, declare the **authoritative valuation
basis** and make every view compute from it. Options: (a) Live report-tab, (b) NAV-tab + CAS,
(c) a defined hybrid. A one-page reconciliation bridging the two must ship in View 8.

## 7. Known gaps & scope delta (surface, don't paper over)
- **RESOLVED 2026-08-24 — IFRS classification + valuation method:** adopted from the accounts
  team (their remit) by parsing the Pack; **26/26 of our live holdings matched**. Extractor:
  `scripts/tracker2/extract_accounts_attributes.py` -> `data/outputs/accounts_team/accounts_attributes.json`.
  These are treated as accounts-team-sourced *attributes* (cited); all *economics* stay on our
  July data (the Pack's own numbers are June 2026 - do not mix).
- **Pack HTML is a richer source than expected:** it also renders, per holding, the Ardent
  independent-valuation coverage flag, opening 1-Jan balances, two-basis movement, fair-value
  reserve, influence band and holding %. Reduces (not eliminates) dependence on the detail xlsx.
- **Scope delta:** Pack = **33 live / 4,551.5m**; our tracker = **26 live / 3,735.4m**. Delta =
  MGX look-through (e.g. MGX I Denali), warrant splits, and names we don't track
  (e.g. Presight/Space42). Tracker 2 shows **our** book; any Pack line we don't hold is listed
  as **not in our data** rather than invented.
- **IFRS classification & valuation method:** not in our data yet (flagged amber in Tracker 1).
  Needed for Views 2 & 8. **Need-data.**
- **The Pack's detail workbook** (`1.G42 and MOZN Investments details - <month>.xlsx`) is **not
  yet located.** Several Pack fields likely originate there. **Need-data / user pointer.**
- **Independently-valued %**, **sub-group / corporate-vs-subsidiary**, **sub-sector** — confirm
  source.

## 8. Metric Dictionary (mandatory artifact, precedes UI)
A single table — one row per metric/field across all views — with: name · definition · formula ·
source field/cell · valuation basis · unit · status (have/derive/need-data/differs). This is the
primary error-prevention control; no view is built until its metrics are dictionary-defined.

## 9. Build sequencing (with sign-off gates)
Each phase ends with **your review + a triangulation check + sign-off** before the next starts —
this is how we don't go off track.
- **P0 — This charter approved** (you sign off scope, names, basis decision R-1).
- **P1 — Metric Dictionary** for Views 1–2 filled; gaps agreed.
- **P2 — Scaffolding:** Tracker 2 shell, entity-scope selector, house-style theme, nav.
- **P3 — View 1 Executive Overview** (reuse Tracker 1 Overview, extend to Pack parity).
- **P4 — View 2 Investment Register** (the depth upgrade, §5).
- **P5 — Views 3–7** (Value Creation, Evolution, Geography, Sector, Concentration).
- **P6 — View 8 IFRS & Audit Trail** (subject to R-1 + IFRS data).
- **P7 — View 9 Change Log + View 10 fold-in of Tracker 1 Portfolio.**
- **P8 — Full triangulation, acceptance, docs, PRD changelog entry.**

## 10. Anti-drift controls (working agreement)
1. One view at a time; no starting the next until the current is signed off.
2. Every change tracked and reported (done / couldn't + why), as we did for the Overview tab.
3. Every figure cited; automated triangulation tests assert section totals == grand total and
   register == summary; a wrong number fails a test before it reaches you.
4. Challenge unsupported claims with evidence (standing expectation).
5. This charter is the source of truth for scope; scope changes are logged here first.

## 11. Definition of Done (per view)
- Visual parity with the Pack view (layout/sections present) in our house style.
- Every figure grounded + cited, or marked pending; units stated; dates in house convention.
- Triangulates to the authoritative basis and to the other views.
- Reviewed and signed off by you.

## 12. Risks & open questions
- **R-1 basis decision** (blocker) — your call needed.
- Missing IFRS data and the Pack detail workbook — need your pointer or a "pending" acceptance.
- Scope delta (33 vs 26) — confirm we present our 26 and list the rest as "not in our data".
- Effort: Views 2 & 8 are the heavy items (register depth + IFRS/audit).

## 13. What I need from you before P1
1. **Approve/edit this charter** (scope, keep/drop/add on the §4 table).
2. **R-1:** pick the authoritative valuation basis (or ask me to recommend one).
3. **Pointers:** where the IFRS classification / valuation method live, and where the Pack's
   detail workbook is — or confirm we proceed with those marked *pending*.
4. **Display title:** confirm "Portfolio Book of Record" or give your own.
