# Session Handoff - read this first at the start of the next session

Last updated: 2026-08-18 (mid-day). This file is meant to be overwritten
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

1. ~~**VTVT** - ~$15M/legal-fee-refund recollection~~ RESOLVED 2026-08-17.
   The new `[INTERNAL] RE G42 - Acceleration of Payment.eml` (caught by
   `scan-for-updates`) plus vTv's audited FY2025 Form 10-K both confirm: on
   28 Feb 2023 G42 paid the deferred $12.5M note early at a 3.75%
   ($468,750) discount, netting $12,031,250 - matching cash flow exactly
   ($12,500,000 + $12,031,250 = $24,531,250 total vs $25M Committed). User
   confirmed this discount (not a legal-fee refund) explains their ~$15M
   recollection/"less than $25M" memory. Committed stays $25,000,000
   (agreed price); register citation (VTVT-EQ-2022) updated to close the
   item; logged in `Listed_Entity_IR_Check_Log.md`.
2. ~~**EsyaSoft** - lifecycle_state stale~~ RESOLVED 2026-08-17 - see below.
3. ~~**EsyaSoft "(Debt)" tranche** and **Mena Mobile Inc "(Debt)" tranche**~~
   RESOLVED 2026-08-17 - both debt tranches added to the register with
   confirmed lifecycle_state and dissolution dates - see section 2c.
4. **Beyond Limits cancellation** - applied per user confirmation, but
   still needs an actual document (side letter, email, board minute, etc.)
   to fully close out per policy (business confirmation is not a
   substitute for a document, only a bridge until one exists).
5. **Fund-level figures deferred by explicit user direction** (separate
   workstream, not a bug): North Summit Capital Fund, New Space Capital GP
   Com SCSp, Acies Investments Fund I, Sinovation Disrupt Fund - tracker
   uses bespoke per-fund tabs, not simple cash-flow sums. MGX (all 4
   vehicles) and New Space Capital Fund I were reviewed and rolled to
   Q2'26 CAS figures 2026-08-17/18 - see section 2c.
6. **ONT's original "Stage 2" tranches** ($30M Oxford + $26.875M JVCo
   contemplated in the 2020 Investment Summary) remain unconfirmed/
   unresolved from an earlier session - a specific G42 TR-1 filing on the
   LSE was never located. Lower priority; flagged in the register long ago.
7. **Explicitly out of scope for now** (user said don't worry about these
   - they're exited): Honor Device Co Ltd, Jollychic Holding Limited,
   X-fusion. Only revisit if the user raises them again.

## 2b. EsyaSoft - RESOLVED 2026-08-17

User asked specifically where the register showed EsyaSoft as "Live" and
why. Traced to the real, working `_build_triangulation_notes()` check in
`cli.py` (compares tracker's own Live/Exited tab per deal vs register's
`lifecycle_state` per entity) - this had already correctly flagged the
mismatch in yesterday's dashboard notes; it was deliberately left unfixed
pending the user's confirmation/documents (per the 2026-08-16 handoff).
User then pointed to the actual closure documents folder:
`...\0. E Q U I T Y\EsyaSoft\2. Transaction Closure Documents`. Read (OCR
where needed - scanned PDFs): `Esyasoft_Resolution_Schedule_A_Final.pdf`
($2.5M convertible debenture, issued 1 Sep 2020), `Executed and dated note
purchase agreement.pdf`, `Investment Apprival_Esyasoft.pdf` (approval form
dated 18 Aug 2020), `MOZN Working Capital Loan.pdf` (loan agreement dated
30 June 2021, USD 411,765.00 - matches the tracker's separate "Esyasoft
Holding (Debt)" cashflow tag exactly).

Changes made:
- `EsyaSoft-NOTE-2020` register row: `lifecycle_state` Live -> Exited,
  `lifecycle_state_date` = 2022-05-10 (matches the tracker's +$5,000,000
  distribution that day - exactly 2x the $2.5M principal, consistent with
  the Debenture's early-payoff/Change-of-Control terms).
- Added new register row `EsyaSoft-WCLOAN-2021` for the previously-missing
  Debt tranche (entity_id EsyaSoft, $411,765, close_date 2021-06-30,
  lifecycle_state Exited, lifecycle_state_date 2022-12-07) - closes part
  of open item #3.
- `register_citations.py` `_DEAL_NAME_TO_INVESTMENT_IDS`: added
  "Esyasoft Holding" -> `EsyaSoft-NOTE-2020` and "Esyasoft Holding (Debt)"
  -> `EsyaSoft-WCLOAN-2021` so the two tracker deal rows don't pool onto
  each other's Committed/citation (same pattern as Cerebras (1)/(2)).
- Ran `list-source-gaps` + `pytest tests/unit -q` (1 passed). Dashboard
  regeneration blocked by the known `PermissionError` gotcha (tracker
  workbook open in Excel) - re-run once closed.

STILL OPEN (not blocking, flagged in the row's `confirmed_by` citation
instead): the tracker's cashflow extract records the $2,500,000 deployment
on 2020-02-09 - 7 months BEFORE the Note Purchase Agreement's actual
1 September 2020 date. Not reconciled - possibly an earlier bridge note
formalized later, or a tracker date-entry issue. This is a cashflow-timing
question (tracker's domain per policy), not a structural register fact,
so left as a citation flag rather than corrected.

## 2c. 2026-08-18 continuation - MGX/New Space Q2'26 update, 3 real bugs fixed

- **Mena Mobile fully closed out** too (same stale-lifecycle_state pattern
  as EsyaSoft): added the missing `MenaMobile-Loan-2021` debt-tranche
  register row ($2,353,982, 7 Apr 2021 Loan Agreement), fixed lifecycle_state
  Live->Exited on both tranches, and confirmed the exact dissolution date
  (30 Sep 2024) from the Cayman Registrar's Certificate of Strike Off the
  user added to the folder.
- **MGX rolled to Q2 2026 CAS basis**: all 4 vehicles' commitment/NAV
  updated from the new Q2'26 Capital Account Statements. Found and
  confirmed (user directed to proceed) a real commitment-transfer event on
  MGX I Strategic Co-Invest LP: $775M -> $296.6M, per the CAS's own
  "Commitment Transfer" footnote (recipient not named). MGX I LP's own
  commitment separately grew to $1,524.15M (ordinary capital-call growth,
  not confirmed to be linked to the Co-Invest transfer - the two changes
  don't net to zero, left as an open question).
- **New Space Capital Fund I** NAV updated from a new Q2'26 EUR-denominated
  Limited Partner Statement (EUR47.54M, ECB rate 1.1394 as of 30-Jun-26).
- **Interim July 2026 capital calls** (Treasury-reported, not yet in any
  tracker file): applied the new roll-forward methodology (see
  `/memories/repo/architecture-policy.md`) to New Space Capital Fund I
  (unambiguous) and to MGX I LP (attributed by triangulating remaining
  unfunded commitment capacity - Strategic Co-Invest and Denali had far
  too little unfunded commitment left to have generated $248.5M in new
  calls). Then, per user request, REVERTED back to pure Q2'26-only figures
  (no July calls) for a clean baseline review - re-apply the July calls
  once the Q2 baseline is confirmed.
- **3 real bugs found and fixed** (see architecture-policy.md for full
  detail): (1) new capital-call cashflow rows entered with the wrong sign
  wrongly inflated Distributions/understated Invested for MGX I LP -
  fixed; (2) MGX I Denali Holding LP was silently absent from the
  dashboard's main Live Investments table (no line item in the tracker's
  own Live/Exited tabs at all) - fixed by injecting a synthetic deal row,
  plus added a fixed MGX display order (LP, Denali, Strategic Co-Invest,
  Group Holding GP) per user preference; (3) dashboard hover-tooltips were
  being clipped by a CSS overflow bug (`.panel`'s `overflow-x:auto` forces
  `overflow-y` to clip too, per spec) - fixed by moving horizontal scroll
  to a `.table-scroll` wrapper around each table instead.
- Confirmed (again, explicitly): we never write to the live/master
  monthly tracker workbook, only read from it.
- `docs/architecture/System_Architecture.md` section 7 and
  `docs/prd/PRD_CHANGELOG.md` v1.9.0 both updated with this work.



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
