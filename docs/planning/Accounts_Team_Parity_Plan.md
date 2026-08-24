# Accounts-Team Dashboard — Parity Analysis & Plan

_Author: IM Platform build session · Date: 2026-08-24_
_Purpose: enumerate everything in the accounts-team dashboard, map it against our own
tabs (Overview, Current month, Company Profiles, Historical, Analytics, Misc), identify
what is missing, and lay out a grounded, phased plan to bring it in — reconstructed for
**our** tracked portfolio (26 live), never approximated._

Source pack analysed: `Accounts Team, G42_Investment_Portfolio_Dashboard_v2.3_21082026.html`
(v2.3, 21 Aug 2026). Their underlying data source is
`1.G42 and MOZN Investments details - <month>.xlsx` (plus the board-deck `.pptx` and the
signed statutory statements). **We have not yet located that detail workbook.**

Scope difference (important, not an error): their pack = **33 live / $4,551.5m**; our
tracker (canonical for us) = **26 live / $3,735.4m**. The delta is MGX look-through,
warrant splits and names we don't track (e.g. MGX I Denali, Presight/Space42).

---

## 1. What the accounts-team dashboard contains

**A persistent entity scope selector** sits above every view:
`Consolidated (33 · 4,551.5m)` · `G42 (22 · 3,630.5m)` · `MGX (4 · 2,003.3m, inside G42)` ·
`MOZN (11 · 921.0m)`. All nine views below re-compute for the chosen entity.

**The nine views and their sub-sections:**

1. **Executive Overview** — _At a glance_ (KPI tiles: current fair value, capital deployed,
   value created + multiple, portfolio growth %, independently-valued %, investment counts,
   movement in period, top-10 concentration, concentration-risk score) · _The portfolio since
   inception_ (FY2020→now line) · _Does it tie back?_ (reconciliation to source Total rows &
   board deck) · _What the portfolio is made of_ (composition by sector, IFRS classification,
   sub-group, corporate/subsidiary, holding-type × IFRS, valuation methodology) · _Where the
   value sits_ (ten largest holdings table) · _How concentrated is it_ (risk score + gauge) ·
   _What stands out_ (auto-generated executive observations).
2. **Investment Register** — one fact sheet per holding: identity, sector, jurisdiction,
   measurement basis, ownership, a **value-creation timeline**, and the **workbook cell each
   figure came from**.
3. **Value Creation** — _What the portfolio has created_ (KPIs) · _Capital deployed against
   fair value_ · _Who created the value, and who lost it_ (ranked) · _Year-on-year movement_ ·
   _Waterfall analysis_ (bridge on two bases).
4. **Portfolio Evolution** — _How the portfolio has evolved_ (since inception) · _What drove
   the change_ (opened/closed each year) · _The portfolio as it stood_ (at any reporting date).
5. **Geography** — _Where the money is_ (exposure by country) · _Regional exposure_
   (region, and region × sector).
6. **Sector** — _What we are exposed to_ (sector & sub-sector) · _Sector growth_ (over time) ·
   _Contribution to value creation_.
7. **Concentration Risk** — _How concentrated is the portfolio_ (weighted 5-measure risk
   score) · _The concentration curve_ · _Single-investment dependency_ · _Concentration by
   dimension_ (holding / geography / sector).
8. **IFRS & Audit Trail** — _The reporting view_ (classification schedule) · _How each holding
   is valued_ · _Reconciliation to the monthly financial reporting pack_ · _Reconciliation to
   the signed financial statements_ (46 caption-year checks, 8 open) · _Basis of preparation_ ·
   _Audit trail_ (processing log).
9. **Change Log** — _Open items_ · _Version history_.

---

## 2. What our tabs contain today

- **Overview** — KPI tiles (fair value, capital deployed, value created + MOIC, live, exited);
  _Live portfolio by holding type_ (equity / loans / funds); _Portfolio value since inception_
  (with a temporary FY20/FY21 estimate); _Where the value sits_ (geography + sector bars);
  _MGX sub-group_ (KPIs + vehicle table); _Ten largest holdings_.
- **Current month** — the embedded tracker dashboard: Live, Exited, Vintage, NAV, All
  Cashflows, Ownership & Domiciliation, Log, Monthly Diff, Glossary — each figure with a
  hover tooltip citing its source cell, column filters and CSV export.
- **Company Profiles** — native, grounded per-company (identity: sector / geography / domicile
  / instrument; economics KPIs; carrying-value history; **cash movements cited to the tracker
  cell**), followed by the visual one-pager cards.
- **Historical** — NAV evolution; Snapshot (KPIs + table, by month & live/exited); Monthly
  diff (cell-level changes).
- **Analytics** — _Value creation_ (KPIs, value-created since inception, who created/lost
  value, capital-vs-fair-value table) · _Concentration_ (value evolution, top-5/10, HHI,
  effective #) · _Portfolio growth_ (NAV since inception, invested-vs-fair-value, quarterly
  cash flows).
- **Misc** — reconciliation (sum of rows vs month total); open action items; source registry
  (SHA-256 fingerprinted); cell-level monthly diff; scope-bridge note.

---

## 3. Gap matrix

| # | Their view / sub-section | Our home today | Status | What is missing | Buildable now? |
|---|---|---|---|---|---|
| A | **Entity scope selector** (Consolidated/G42/MGX/MOZN) | — (MGX panel only) | ❌ | Persistent scope toggle re-computing every view | ✅ we hold `investing_entity` / `section` |
| B | Exec Overview → _At a glance_ | Overview KPIs | 🟡 | growth %, movement-in-period, independently-valued %, risk score tile | ✅ (except independently-valued %, needs Ardent data) |
| C | Exec Overview → _Does it tie back?_ | Misc reconciliation | 🟡 | tie-out to sheet Total rows / board deck | ⚠️ needs detail workbook + board deck |
| D | Exec Overview → _What it's made of_ | Overview holding-type + geo/sector | 🟡 | IFRS class, valuation methodology, corporate/subsidiary, sub-group | ⚠️ IFRS/valuation need source; sub-group ✅ |
| E | Exec Overview → _What stands out_ | — | ❌ | auto-generated executive observations | ✅ templated from our metrics |
| F | **Investment Register** (fact sheet + value-creation timeline + source cell) | Company Profiles | 🟡 | per-holding value-creation timeline; full sortable register table | ✅ we have monthly history + citations |
| G | Value Creation → _Year-on-year movement_ | — | ❌ | YoY movement table | ✅ from monthly series (our window) |
| H | Value Creation → _Waterfall analysis_ | — | ❌ | opening→additions→value-change→closing bridge | ✅ from series + cashflows (our window) |
| I | Portfolio Evolution → _What drove the change_ | — | ❌ | opened / closed each year | ✅ from vintage + exit timing (our window) |
| J | Portfolio Evolution → _As it stood_ | Historical snapshot | 🟡 | as-at snapshot pre-Sep'22 | ⚠️ needs FY20/21 data |
| K | **Geography** view | Overview geo bars | 🟡 | region grouping; region × sector | ✅ needs a country→region lookup |
| L | **Sector** view | Overview sector bars | 🟡 | sub-sector; sector growth over time; sector contribution to value | ✅ growth/contribution; ⚠️ sub-sector may need a map |
| M | **Concentration Risk** (weighted score + gauge + curve + dependency) | Analytics HHI/top-5/10 | 🟡 | weighted 5-measure score, gauge, Lorenz curve, ex-top-N view | ✅ we now hold geography/sector/holdings shares |
| N | **IFRS & Audit Trail** | Misc registry/reconciliation | ❌ | IFRS classification schedule, basis of prep, tie-out to signed statements | ⚠️ needs IFRS class + statutory data |
| O | **Change Log** | Misc action items + cell-diff | 🟡 | structured open-items / version history | ✅ light |

Legend: ✅ have / straightforward · 🟡 partial · ❌ missing · ⚠️ blocked on an external source.

---

## 4. Plan to close the gaps

### Phase 0 — buildable now from data we already hold (no new source)
1. **Entity scope selector** (gap A) — a persistent `Consolidated / G42 / MGX / MOZN` control
   (map: MGX = `G42 Holding` / MGX section; MOZN = `Mozn`; G42 = the rest) that filters
   Overview, Analytics and Company Profiles. _Biggest single parity win._
2. **Concentration Risk** (gap M) — weighted 5-measure score (top-5, HHI, largest holding,
   largest jurisdiction, largest sector) with gauge + banding, concentration curve, and an
   "ex-largest-N" view.
3. **Value Creation → YoY movement + Waterfall** (gaps G, H) — from our monthly series and
   cited cash flows, over our data window.
4. **Investment Register** (gap F) — a full sortable register table, plus a per-holding
   **value-creation timeline** on the Company Profiles page (we have the monthly history).
5. **Executive observations** (gap E) — a short, templated narrative generated from our own
   grounded metrics (concentration, geography, holder split).
6. **Geography & Sector views** (gaps K, L) — promote to first-class: add a country→region
   lookup (region + region × sector), sector growth over time, and sector contribution to
   value creation.
7. **Portfolio Evolution → opened/closed per year** (gap I) — from vintage and exit timing
   within our window.

### Phase 1 — light data work
8. **Composition depth** (gap D, partial) — corporate/subsidiary and sub-group splits from
   `section`/`investing_entity`; sub-sector via a small curated map if we want it.
9. **Change Log structure** (gap O) — formalise open-items + a version/build history.

### Phase 2 — blocked on an external source (track in Misc → action items)
10. **IFRS & Audit Trail** (gap N) + **valuation methodology / independently-valued %**
    (gap D) — need the detail workbook's IFRS classification and the Ardent valuation data.
11. **Tie-out to source Total rows, board deck and signed statements** (gap C) — needs
    `1.G42 and MOZN Investments details - <month>.xlsx`, the board-deck `.pptx`, and the
    statutory statements.
12. **Pre-2022 history & as-at snapshots** (gap J) — replace the temporary FY2020/FY2021
    estimate with real per-investment NAVs (and add positions exited before Sep'22).

### Standing data asks (from the user)
- Real **FY2020 / FY2021 investment NAVs** (temporary estimate currently on the chart).
- The **`1.G42 and MOZN Investments details - <month>.xlsx`** detail workbook (unlocks
  Phase 2 entirely: IFRS class, valuation methodology, statutory reconciliations, and the
  full wider-scope reconciliation to their 33 / $4,551.5m).

---

_Principle throughout: every figure stays traceable to the tracker (or a named source),
reconstructed for our 26-name portfolio; anything we cannot ground is labelled and parked,
never estimated silently._
