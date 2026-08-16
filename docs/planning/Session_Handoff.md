# Session Handoff - read this first at the start of the next session

Last updated: 2026-08-16 (end of day). This file is meant to be overwritten
at the end of each working session - it is the single "where did we leave
off" reference, complementing (not duplicating) the durable policy already
captured in `docs/prd/PRD_v1.md` and repo memory.

## 0. First thing to do next session

1. Run `scan-for-updates` before anything else (standing practice - see
   PRD_v1.md section 19.4):
   ```
   .\.venv\Scripts\python.exe -m im_platform.cli scan-for-updates --investments-root "C:\Users\divyesh.mahajan\OneDrive - G42\Desktop\0.1 SPPM ###\1. I N V E S T M E N T S  -  Global (Ex China)"
   ```
2. If the user wants a fresh dashboard, regenerate with the latest monthly
   tracker file (check `1. Main (monthly report)` for the newest dated
   subfolder / highest version number):
   ```
   .\.venv\Scripts\python.exe -m im_platform.cli generate-tracker-dashboard --tracker-file "<latest tracker path>"
   ```
   **Gotcha**: this fails with `PermissionError` if the tracker workbook is
   open in Excel on the user's machine. Don't loop-retry more than twice -
   tell the user and move on to other work, retry later.

## 1. What was accomplished today (2026-08-16)

A full working session covering: foundational architecture documentation,
a folder restructure (source-of-truth vs regenerable outputs), a
"scan-for-updates" deletion/rename detection upgrade, and then a long,
systematic re-verification pass on vintage years and commitment amounts
across the equity portfolio against primary/signed documents.

### Entities fully re-verified against primary documents today
HeyGears, Beyond Limits (2 tranches), EsyaSoft, Flyr, Jysan Technologies,
Life Biosciences (citation clarified, no number change), Glass Earth
(citation bug fix only), Neuralink (Project Cortex), vTv Therapeutics
(VTVT - also cross-checked against a public IR press release), ONT,
Liquid AI, School Hack, Mena Mobile (currency re-confirmed).

### Real bugs found and fixed along the way
- `register_citations.py` `short_citation()`: two false-positive
  "unverified" downgrades fixed (term-sheet mention and "AI-extracted"
  prefix were overriding an already-CONFIRMED citation) - see
  `/memories/repo/architecture-policy.md` for the exact fix.
- Double-counting bug when one position spans >1 tracker deal row (e.g.
  TFH-Worldcoin/WLD Tokens, Cerebras (1)/(2)) - fixed via
  `_deal_cashflow`/`_deal_valuation` granular matching.
- ONT's Committed was silently excluding a GBP-denominated tranche from
  the USD total - now explicitly flagged when it happens (not silently
  dropped).

### User-confirmed business decisions applied
- **Beyond Limits**: the final ~$10M Series C tranche is cancelled (no
  further investment intended) - Committed now pinned to Invested ($90M,
  zero Remaining). No cancellation document on file yet - user said they
  will try to obtain one.
- **ONT**: the JVCo co-investment never materialized - same treatment
  (Committed = Invested = $141.5M, zero Remaining).

### Where I challenged the user instead of just complying (per their
explicit "watchful eye" instruction - see PRD_v1.md section 26 and
`/memories/collaboration-style.md`)
- **Mena Mobile**: user recalled possibly AED 8M - the executed SPA's
  Schedule II explicitly states USD 8,000,000. Kept USD, logged the query.
- **vTv Therapeutics**: user recalled a possible $15M figure / legal-fee
  refund - found no supporting evidence in the press release, 8-K, or
  cash flow. Kept the document-verified $25M, logged as an open item.

## 2. Open items / unresolved (in priority order for tomorrow)

1. **VTVT** - user's recollection of a ~$15M figure / possible
   legal-transaction-fee refund is unconfirmed. Committed stays at $25M
   until the user provides a document or clearer detail.
2. **EsyaSoft** - user believes this has since EXITED at ~2x ($2.5M in,
   evidence of a +$5,000,000 cash flow on 2022-05-10 already exists) -
   register still shows `lifecycle_state = Live`. User said they'll
   provide more detail - do not change lifecycle_state without it.
3. **EsyaSoft "(Debt)" tranche** and **Mena Mobile Inc "(Debt)" tranche** -
   both have real cash flow under a separate `investment_id` tag with no
   corresponding register row yet (Committed shows tracker's own smaller
   figure vs a gap). Not yet investigated.
4. **Beyond Limits cancellation** - applied per user confirmation, but
   still needs an actual document (side letter, email, board minute, etc.)
   to fully close out per policy (business confirmation is not a
   substitute for a document, only a bridge until one exists).
5. **Fund-level figures deferred by explicit user direction** (separate
   workstream, not a bug): MGX I Strategic Co-invest, MGX I LP, North
   Summit Capital Fund, New Space Capital Fund I, New Space Capital GP Com
   SCSp, Acies Investments Fund I, Sinovation Disrupt Fund - tracker uses
   bespoke per-fund tabs, not simple cash-flow sums (verified against the
   tracker's own formulas).
6. **ONT's original "Stage 2" tranches** ($30M Oxford + $26.875M JVCo
   contemplated in the 2020 Investment Summary) remain unconfirmed/
   unresolved from an earlier session - a specific G42 TR-1 filing on the
   LSE was never located. Lower priority; flagged in the register long ago.
7. **Explicitly out of scope for now** (user said don't worry about these
   - they're exited): Honor Device Co Ltd, Jollychic Holding Limited,
   X-fusion. Only revisit if the user raises them again.

## 3. Standing practices to keep applying (already in PRD/memory, listed
here as a quick-glance reminder)

- Run `scan-for-updates` at the start of every session and before
  finalizing any month-end report.
- `data/source_of_truth/` = durable, never wholesale-regenerated.
  `data/outputs/` = fully regenerable, safe to delete.
- Vintage/close date: always check contract signing date vs. a separately
  stated closing date vs. actual cash movement date vs. tracker's own
  value - they can genuinely diverge by months/years.
- Exact cash-flow amount matches are the strongest confirmation available
  - prioritize over narrative summaries.
- For listed entities (ONT, VTVT), check IR pages/public filings
  proactively and log it in
  `data/source_of_truth/Listed_Entity_IR_Check_Log.md`.
- Challenge unverified claims - from documents AND from the user's own
  recollection - rather than silently accepting or silently overriding.
- After any register edit: `list-source-gaps`, then regenerate the
  dashboard, then `pytest tests/unit -q`.
- Known gotcha: `apply-reconciliation` regenerates
  `Tracker_Extract_Reconciled.xlsx` from scratch, wiping any manually
  added valuation row (e.g. `MANUAL-VAL-0001` for MGX Denali) - re-add
  after every run.

## 4. Where the durable detail lives (don't re-derive, read these first)

- `docs/prd/PRD_v1.md` section 19.4 (source-of-truth hierarchy), 19.5
  (vintage/commitment verification discipline), section 26 (product
  principles, including the challenge discipline).
- `docs/architecture/System_Architecture.md` - full pipeline/adapter
  reference.
- `/memories/repo/architecture-policy.md` - condensed technical notes on
  every bug fixed and mechanism added this week (deal-splitting, the
  `_COMMITTED_EQUALS_INVESTED_DEALS` override, citation bugs, etc.)
- `/memories/collaboration-style.md` - the "challenge, don't just comply"
  working relationship principle.
- `data/source_of_truth/Listed_Entity_IR_Check_Log.md` - public filing
  checks for listed entities.
