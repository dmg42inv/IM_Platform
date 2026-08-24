# Session Status & Handoff — 2026-08-23 (EOD)

Quick-resume note. Two active workstreams. Pick up from **Tomorrow's plan** below.

---

## Workstream A — Sandbox citation-grade Legal Knowledge Base  ✅ built
- Legal KB fully built: **27/27 deals, 0 failures** → `data/legal_kb/legal_kb.sqlite` (~557 MB).
  3,632 docs, 130,515 nodes, 121,803 citations, 181,570 embeddings.
- Pipeline (`scripts/legal_kb/`): `build_kb` → `query` (hybrid BM25+FAISS) → `grounding`
  (PRD §19.7 verbatim-number gate) → `domicile` → `dgml_export`.
- Clean reorg done: `_RS\CLEAN\{0_Equity|1_Funds}\<Name>\{00_Knowledge_Base + 01–11 buckets}`.
  Originals untouched in `_RS\AF\...\99_Archive`.

### Recent (2026-08-23): domicile extractor hardened  ✅
After user challenged Cerebras/Neuralink/DriveNets, root-caused via direct KB text search and fixed
`scripts/legal_kb/domicile.py`:
- Context tightened to **incorporation verbs only** (was mis-reading governing-law "laws of California").
- Added **Israel + demonyms** ("an Israeli company"), **two-tier strong/weak ranking**, multi-word capture,
  negation/securities guards, dropped noisy "registered in" fallback.
- **Now correct + cited:** Cerebras→Delaware, Neuralink→Nevada, DriveNets→Israel, InstaDeep→England&Wales,
  Beyond/Liquid/Flyr/vTv→Delaware, HeyGears→China, Esyasoft→DIFC, New Space→Luxembourg, Sinovation/Mena→Cayman.
- `scripts/legal_kb/export_domicile.py` → `data/source_of_truth/company_domicile_legal.json` (grounded, cited,
  status=candidate, top-alt shown). `_SKIP_DEALS` (fall back to tracker): Tools for Humanity, WLD Tokens,
  **Life Biosciences** (US co; folder describes the ADGM/GAML holding SPV).
- **NEEDS ANALYST CONFIRM (holdco/SPV vs operating co):** Inveniam=ADGM(alt Delaware), North Summit=China(fund is
  Cayman), Jysan=England(operating Kazakhstan), Verses=California. AAICO/School Hack(AIREV)/MGX = ADGM is correct.

---

## Workstream B — Tracker-style dashboard (Company Profiles)  ✅ shipped this session
File: `src/backend/im_platform/adapters/tracker_style_dashboard.py` → `data/outputs/Tracker_Style_Dashboard.html`.
- **Company Profiles tab**: master-detail rail + one-pager cards.
- Left rail **segmented Equity / Funds, with MGX as a sub-group** (note: 4 MGX vehicles incl. the GP entity).
- **Domicile sourced from legal docs** (grounded, cited, "candidate – confirm"), tracker fallback when suppressed.
- **NAV + Cashflow charts side-by-side**; cashflow chart draws **cash-out (red) and cash-in (blue) upward from $0**.
- Descriptive facts (website/sector/HQ/description) in `data/source_of_truth/company_descriptive_facts.json`,
  each source-labeled. **Done: 5 flagship** (Oxford Nanopore, Cerebras, Neuralink, DriveNets, InstaDeep).
  **TODO: remaining ~24 companies' descriptions** (Wikipedia/web, labeled).
- Regenerate: `python -m im_platform.cli generate-tracker-dashboard --tracker-file "<Jul'26 xlsx>"`

---

## Workstream C — Portfolio time-series DB + localhost app  🚧 Phase 1 done
Goal: ingest ALL monthly trackers into SQLite for time-series (NAV evolution) + dynamic localhost (Streamlit) app.
- **Built** `scripts/portfolio_db/ingest_trackers.py` → `data/portfolio/portfolio.sqlite`.
  Tables: `tracker_months` (per-month + parse status), `monthly_positions` (1 row/deal/month).
  Idempotent. Run: `python -m scripts.portfolio_db.ingest_trackers`
- **Coverage now: 21/46 months** (all 2025 + 2026 + 2024 Oct/Dec). Clean NAV series **Oct'24 $900m → Jul'26 $3.7bn**.
- **Blocked on 2022–2024 backfill:** those workbooks were OneDrive **cloud-only** (`Errno 22`). User set "always keep
  on this device"; I also ran `attrib +P -U` on FY2022/23/24 folders → **downloading in background overnight**.
- Monthly folders live under `…\0.2 Portfolio Management - Monthly\1. Main (monthly report)\` in FY archives
  (`1.1 FY 2022` … `1.5 FY 2025`, plus top-level `2.x` for 2026). Naming varies; date "DD Mon YY" is the common key.
- Legacy format: a few downloaded pre-2025 files use **different sheet names** (no `1. Live`/`2. Exited`) → need
  parser variants.
- **Streamlit app** exists (`src/frontend/streamlit_app.py`, login gate, runs at `localhost:8501`) but only shows the
  snapshot table — not yet wired to `portfolio.sqlite` or the Company Profiles view.

---

## Tomorrow's plan (in order)
1. **Confirm OneDrive finished downloading** FY2022–2024:
   `Get-ChildItem "<main root>" -Recurse -Filter "*Portfolio Summary*.xlsx" | ? { $_.Attributes.value__ -band 0x400000 }`
   (should be empty). Then re-run `python -m scripts.portfolio_db.ingest_trackers`.
2. **(A) Backfill older years:** for months still failing with "Worksheet '1. Live' not found", add legacy-sheet-name
   parser variants in `im_platform.adapters.live_exited_sections` (detect old tab names/layout). Target full
   Sep'22 → Jul'26 coverage in `portfolio.sqlite`.
3. **(B) Wire Streamlit → portfolio.sqlite:** NAV-evolution view first (line/area of live_carrying over months),
   then progressively fold in Company Profiles. Serve at `localhost:8501`.
4. Continue sourcing the remaining ~24 company descriptions.
5. Analyst-confirm the flagged domiciles (Inveniam, North Summit, Jysan, Verses).

## PRD / docs
- PRD updated to **v1.16.0** (changelog): grounded-domicile hardening + portfolio time-series ingestion +
  Company Profiles view. See `docs/prd/PRD_CHANGELOG.md`.
- Full detail also in repo memory: `/memories/repo/RESUME_two_workstreams_2026-08-22.md`.
