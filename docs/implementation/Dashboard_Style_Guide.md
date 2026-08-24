# Investments Portfolio Dashboard — Style & Formatting Guide

Status: living document · Owner: IM Platform · Last updated: 2026-08-24
Applies to: `src/frontend/streamlit_app.py` (and the embedded HTML dashboards).

This guide captures the presentation conventions agreed while building the
**Overview** tab so the same standard can be applied to every other tab
(Current month, Company Profiles, Historical, Analytics, Misc, Parking) without
re-deciding each time.

---

## 1. First principle — everything is grounded

- Every figure on screen must trace back to the **monthly Portfolio Summary**
  (the Live / Exited register) — our single source of truth for the book.
  No approximations, no fabricated values.
- Counts and totals are **data-driven** (`len(live)`, `carrying_value.sum()`,
  etc.), never hardcoded. If a scope legitimately yields an unusual number
  (e.g. MOZN = 10 live / 10 exited), show it — do not "round" it.
- Where a value is **not** from the Portfolio Summary (e.g. the temporary
  FY2020–FY2021 estimate on the since-inception chart), it must be visibly
  flagged as an estimate and never presented as sourced fact.

## 2. Tone & terminology (SEC / investment-banking register)

Write captions and notes as a senior IB professional drafting a note for an
external, regulated reader.

Do **not** use internal shorthand on screen:

| Avoid (internal) | Use instead |
|---|---|
| "tracker", "our tracker", "monthly trackers" | "the monthly Portfolio Summary" |
| "grounded on …" | "sourced from …" / "derived from …" |
| "Auto-generated …" | "Derived from the underlying portfolio figures" |
| "tracked names" | "holdings" / "investments" |

- Prefer precise outcomes: distinguish **realised** vs **written off** rather
  than lumping as "exited / written off".
- Distinguish **live (unrealised)** investments explicitly.
- State the unit once, clearly: "Amounts in USD millions".
- Never over-claim: if any figure in a view is estimated, the grounding note
  must say so ("Prior-year figures, where indicated, are estimated.").

## 3. Page layout

- **Page title + scope tabs on one row**, bottom-aligned:
  `st.columns([1.5, 5], vertical_alignment="bottom")` — serif `<h1>` on the
  left, the entity-scope `segmented_control` (Consolidated / G42 / MOZN / MGX)
  on the right. Scope tabs render inside the scoped section body, not the header.
- **Nav** (Overview, Current month, …) is styled as **binder/folder tabs** so it
  reads differently from the scope filter.
- **Section boxes are 3D**: wrap each logical section in
  `with st.container(border=True):`. These are styled via
  `[data-testid="stVerticalBlockBorderWrapper"]` with a soft drop-shadow,
  14px radius, theme-aware fill. (Do not rely on volatile `.st-emotion-cache-*`
  class names alone — always include the stable `data-testid` selector.)

## 4. KPI blocks

- Group the headline KPIs inside a single bordered section box.
- Use **equal-width** columns (`st.columns(5)`) with `st.metric(..., border=True)`.
- A small **right-aligned "Fair value as of {month}"** timestamp sits at the top
  of the box (not a verbose title line).
- KPI values must **never truncate**: metric value font is capped
  (`[data-testid="stMetricValue"] { font-size:1.65rem; white-space:nowrap;
  overflow:visible; }`).
- Two caption lines beneath the KPIs: (1) the exclusion note (live vs
  realised/written-off), (2) the units + source + estimate caveat.

## 5. Metric definitions (use consistently)

| Label | Definition |
|---|---|
| Current fair value | Sum of Live carrying value |
| Capital deployed | Sum of Live invested |
| Value created | Fair value − invested (Live) |
| **Gross MOIC (TVPI)** | (distributions + fair value) ÷ invested. Labelled "(TVPI)" so an external reader is not misled — it includes distributions. |
| Live investments | Count of distinct Live deals |
| Realised / written off | Count of distinct Exited deals (shown as an exclusion note, not a KPI box) |

## 6. Entity scopes

- **Consolidated** = all holdings.
- **MOZN** = section contains "MOZN".
- **MGX** = section contains "MGX" or deal type starts "MGX".
- **G42** = everything not MOZN (MGX sits inside G42).
- Charts that are trivial for single-entity scopes (e.g. by-holder for MGX/MOZN)
  should adapt (e.g. switch to "by holding").

## 7. Charts

- Palette: G42 green-led (`#2F6B45`; loss/negative `#b3253a`); sequential greens
  for heatmaps. Font is EB Garamond, inherited from `.streamlit/config.toml`
  (config font reaches charts; injected CSS does not).
- Horizontal category bars via the `_bar_h` helper: rounded bar ends,
  **formatted `$` tooltips**, explicit axis titles, no chartjunk.
- Always label axes; never leave a bare numeric axis.
- Amounts in tooltips/labels formatted to 1 decimal, `$` + thousands separators.

## 8. Tables

- Use the `_html_table` helper for presentation tables — **centre-aligned**
  (`st.dataframe` cannot centre-align), `.g42-tbl` styling, uppercase light
  headers, thin row separators.
- Money columns: `$%,.1f`; multiples: `%.2fx`; shares/weights: `%.1f%%`.
- State "USD millions" once per section, not per row.
- For wide "largest holdings"-style tables, centre the table in
  `st.columns([1, 3, 1])`.

## 9. Gotchas

- **LaTeX `$` collision**: Streamlit reads a paired `$…$` in markdown/captions as
  math. When a caption contains two or more dollar amounts, escape with
  `.replace("$", "\\$")`. (`st.metric` is not affected.)
- `use_container_width` is deprecated → use `width="stretch"`.
- Config (`.streamlit/config.toml`) changes require a **server restart**; Python
  code changes hot-reload.

## 10. Known temporary items to carry forward

- **FY2020–FY2021** points on since-inception charts are a **temporary estimate**
  pending our own historical NAVs; always shown dashed/orange and flagged.
- Sector/geography history only exists from Jun'26 onward in the Portfolio
  Summary; do not plot sector-over-time until backfilled.
