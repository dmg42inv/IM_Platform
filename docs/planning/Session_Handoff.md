# Session Handoff - read this first at the start of the next session

Last updated: 2026-08-19 (evening). This file is meant to be overwritten at
the end of each working session - it is the single "where did we leave off"
reference, complementing (not duplicating) the durable policy already
captured in `docs/prd/PRD_v1.md`, `docs/prd/PRD_CHANGELOG.md`, and repo
memory (`/memories/repo/architecture-policy.md`).

## What was done this session (2026-08-19)

1. **New Space Capital Fund I / GP Com SCSp - full resolution** (carried
   over from the previous evening, finished today): confirmed the true
   Fund S.C.S. commitment (EUR 23,234,461.87) via 3 independent documents,
   separated the two distinct legal vehicles that were pooling into one
   citation, fixed 3 separate FX bugs (Fund S.C.S. commitment rate, Fund
   S.C.S. Carrying Value ignoring an existing FX field, GP Com SCSp's
   commitment/invested needing a DIFFERENT fixed rate than the main Fund),
   and refined Invested/Distributions using the CAS's net contributions
   plus traced actualisation-interest cash payments. Full detail in repo
   memory.
2. **Exited-position structural rule**: Committed is now pinned to
   Invested for EVERY deal in the tracker's Exited tab - Remaining is
   always 0 for a fully exited position. Verified across all 12.
3. **New "Vintage" tab**: groups all Live+Exited deals by vintage year
   instead of investing entity, per-vintage subtotal + blended IRR + grand
   total. Kept, still in the dashboard.
4. **"Vintage 1" tab - built, then fully removed same session** at user
   request (was a Live-only, MGX-excluded filtered view). Nothing left
   over from it.
5. **New "NAV" tab**: as-of-date NAV view grouped by asset Type (Listed /
   Fund / PE), with Live and Exited kept in separate sections.
   - Type comes from the tracker's own "NAV" sheet (the only place that
     classification exists) via new `extract_nav_sheet()` in
     `tracker_supplementary_tabs.py`.
   - Carrying Value and the Comment (source/last-revised note) are BOTH
     the platform's own data, never the tracker's raw NAV-sheet text -
     `recompute_deal_financials` now also captures each deal's
     `assumption_note`/`valuation_date` from the exact Valuation_Extract
     row used for Carrying Value. This was a real bug caught during
     review: the tracker's own NAV-sheet Comment for Acies still said
     "Q1'26 capital account statement" even though we'd already rolled
     Acies's NAV forward to Q2'26 ourselves - now fixed to always show
     the platform's own most recent action, not an external system's
     possibly-stale account of it.
   - `MGX I Denali Holding LP` shows "Not classified" (correctly - it's
     absent from the tracker's own NAV sheet, same reason it's a
     synthetic row not in the tracker's report tabs at all).
6. **Glossary tab**: reduced from 4 columns to 2 (Display Name, Full Legal
   Name only) per user request.
7. **Acies**: rolled NAV forward from Q1'26 to the newly-added Q2'26
   Capital Account Statement ($12,683,716 -> $14,034,903).
8. Architecture discussion (agreed, NOT yet built): a monthly snapshot +
   period-over-period diff design - see "Next up" below.
9. Updated `docs/prd/PRD_CHANGELOG.md` (v1.12.0) and
   `docs/architecture/System_Architecture.md` (section 9) with this
   session's structural learnings, generic per the no-deal-names policy.

## Next up / not yet done

- **Monthly snapshot + period-diff feature** (architecture agreed, not
  built): persist a per-deal-per-month snapshot workbook so a "what
  changed since last month" view/tab can be computed without re-deriving
  everything. Design: cumulative `Portfolio_Snapshot_History` (one row
  per deal per month, post-correction figures), auto-appended by
  `generate-tracker-dashboard`, new diff step classifying deals
  New/Exited/Changed with notable-change flags, presented as both a
  dashboard tab and a standalone file. Two open design questions the user
  hasn't given a final answer on: (a) per-deal snapshot only, or also a
  portfolio-level rollup row? (b) permanent dashboard tab, standalone
  file, or both? Ask before building.
- New Space Capital GP Com SCSp's Carrying Value ($3,858,379) still
  doesn't reconcile to either EUR NAV figure found in the fund's own NAV
  calc PDF - not resolved, source of that number not traced. Revisit if
  the user raises Carrying Value for this deal again (see repo memory for
  full detail).

## Known standing gaps (not new, still open)

- North Summit: aggregate CAS override applied and correct, but
  underlying dated cashflow rows still don't individually tie out to the
  CAS (needs capital call/distribution notices not yet located).
- Cerebras Systems Inc (2): blank IRR / absurd TVPI (near-zero cost
  basis, $698M mark) - same root-cause class as the Tools for Humanity
  fix (XIRR bisection bracket too narrow for extreme gains) but not
  fixed - low priority, not requested.
- New Space Capital Fund I: ~20 total drawdown notices imply several more
  portfolio-company sub-investments funded under the one consolidated
  Fund commitment, none individually broken out in the register beyond
  the one Fund-level row - flagged, not required to fix further.

## Standing practices (unchanged, keep following)

- Tracker file frequently locks (open in Excel) - don't retry
  `generate-tracker-dashboard` more than twice per attempt; ask the user
  to close it.
- Always clean up temporary one-off Python scripts (`_tmp_*.py`) after
  use.
- Keep `PRD_CHANGELOG.md` / `System_Architecture.md` fully generic (no
  deal names) per user policy - specifics go in
  `/memories/repo/architecture-policy.md`.
- Run `pytest tests/unit -q` after any code change; regenerate + spot-
  check the dashboard before considering a fix complete.
- Git commit/push only when the user asks, with descriptive messages.
- Terminal quirk: PowerShell here sometimes echoes a truncated fragment
  of the command instead of real output, especially with long OneDrive
  paths containing spaces/special characters. Reliable workaround: write
  a small `_tmp_*.py` script and run it via
  `& ".\.venv\Scripts\python.exe" "_tmp_script.py"` instead of inline
  `python -c "..."` with complex quoting.
- **General lesson from this session**: when displaying "why is this
  number what it is" (a source/last-revised note), always point at the
  platform's own most recent action on that figure, not an external
  system's (the tracker's) account of it - the external note can go
  stale the moment we roll something forward ourselves.

## Exact command to regenerate the dashboard

```
.\.venv\Scripts\python.exe -m im_platform.cli generate-tracker-dashboard --tracker-file "C:\Users\divyesh.mahajan\OneDrive - G42\Desktop\0.2 Portfolio Management - Monthly\1. Main (monthly report)\2.7 31 Jul 26\1. Portfolio Summary Jul'26 v2.0.xlsx"
```
