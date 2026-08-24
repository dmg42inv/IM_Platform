# Session Handoff - read this first at the start of the next session

Last updated: 2026-08-20. This file is meant to be overwritten at
the end of each working session - it is the single "where did we leave off"
reference, complementing (not duplicating) the durable policy already
captured in `docs/prd/PRD_v1.md`, `docs/prd/PRD_CHANGELOG.md`, and repo
memory (`/memories/repo/architecture-policy.md`).

## What was done this session (2026-08-20)

1. **Monthly snapshot + month-over-month diff feature built**:
   - New adapter: `src/backend/im_platform/adapters/monthly_snapshot.py`.
   - `generate-tracker-dashboard` now persists a cumulative
     `data/source_of_truth/Portfolio_Snapshot_History.xlsx` workbook with
     one row per deal per snapshot month, using the final post-recomputed
     dashboard figures (not the tracker's raw Live/Exited report outputs).
   - Same command also writes
     `data/outputs/Portfolio_Monthly_Diff.xlsx`, comparing the latest two
     snapshot months and classifying changes as New / Exited / Changed /
     Removed with per-metric deltas.
   - New dashboard tab: **Monthly Diff**, backed by the same latest diff
     DataFrame and downloadable as CSV.
   - Same-month reruns replace that month's rows rather than duplicating
     them, so regenerated/corrected monthly numbers stay canonical.
   - Added `backfill-monthly-snapshot` CLI command for deliberate
     historical month backfills from one or more tracker workbooks.
   - Backfilled June 2026 from the highest-version June workbook; history
     now contains `2026-06` and `2026-07` (78 rows total), and latest diff
     contains 12 June-to-July changed rows.
2. Ran the standing document update scan on 2026-08-20: no new company or
   fund folders, no modified/deleted/renamed files, but 5 added files were
   detected and the manifest/report were refreshed.
3. Regenerated `data/outputs/Tracker_Style_Dashboard.html` successfully.
  Current generated snapshot history contains 39 rows each for `2026-06`
  and `2026-07`; Monthly Diff is populated for June-to-July.
4. **Local Streamlit app built and smoke-tested**:
  - Entry point: `src/frontend/streamlit_app.py`.
  - Browser login via `st.secrets` or `IM_PLATFORM_APP_USER` /
    `IM_PLATFORM_APP_PASSWORD` environment variables.
  - Snapshot mode: month dropdown + All/Live/Exited filter + KPI row +
    downloadable table.
  - Monthly diff mode: latest comparison cards + downloadable diff table.
  - Running locally at `http://localhost:8501` in this session with
    temporary demo credentials (`demo` / `demo`) only.
5. Validation run:
   - `pytest tests/unit/test_monthly_snapshot.py -q` -> 2 passed.
   - `pytest tests/unit -q` -> 3 passed.

## Next up / not yet done

- **Replace demo localhost credentials** before any real use beyond this
  coding session. Use `.streamlit/secrets.toml` (ignored by Git) or local
  environment variables.
- New Space Capital GP Com SCSp's Carrying Value ($3,858,379) still
  doesn't reconcile to either EUR NAV figure found in the fund's own NAV
  calc PDF - not resolved, source of that number not traced. Revisit if
  the user raises Carrying Value for this deal again (see repo memory for
  full detail).

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
