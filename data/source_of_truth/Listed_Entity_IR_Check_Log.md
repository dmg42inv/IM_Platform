# Listed Entity IR Check Log

Durable log of investor-relations page / public filing checks performed for
portfolio companies that are publicly listed. Update this whenever a listed
entity's figures are being verified or re-checked, so we don't lose track of
what's already been checked and don't re-do the same lookup unknowingly.

Currently known listed entities in the portfolio: **ONT plc** (Oxford
Nanopore, LSE), **vTv Therapeutics Inc.** (Nasdaq: VTVT).

| Date | Entity | Ticker/Exchange | Source checked | Finding | Action taken |
|---|---|---|---|---|---|
| 2026-08-16 | vTv Therapeutics | Nasdaq: VTVT | [IR press release, 1 Jun 2022](https://ir.vtvtherapeutics.com/news-releases/news-release-details/vtv-therapeutics-announces-investment-and-entry-collaboration) | Confirms $25M investment by G42 Investments AI Holding RSC Ltd; $12.5M cash at closing + $12.5M due 31 May 2023; $30M FDA-approval-contingent milestone (not $20M as an earlier draft suggested) | Updated register citation (VTVT-EQ-2022): confirmed entity name, close date 2022-05-31, corrected milestone figure to $30M |
| 2026-08-17 | vTv Therapeutics | Nasdaq: VTVT | [FY2025 Form 10-K, filed 10 Mar 2026](https://www.sec.gov/Archives/edgar/data/1641489/000164148926000010/vtvt-20251231.htm), audited (Ernst & Young) | Confirms G42 Purchase Agreement terms exactly (259,657 shares, $25.0M, $12.5M cash + $12.5M promissory note). Confirms 28 Feb 2023 amendment: note paid early, $12.0M received reflecting a 3.75% discount ($468,750 on the $12.5M), in full satisfaction of the note, GAAP loss of $0.3M. Matches internal email (13 Feb 2023, "G42 - Acceleration of Payment") and actual recorded cash flow ($12,500,000 + $12,031,250 = $24,531,250 total vs $25M Committed) exactly. | Closed the open item re: user's ~$15M/legal-fee-refund recollection - user confirmed 2026-08-17 it was this early-payment discount, not a legal-fee refund. Updated register citation (VTVT-EQ-2022) to mark resolved; Committed stays $25,000,000 (agreed price), ~$468,750 gap vs actual cash invested is a confirmed permanent discount, not unfunded commitment. |

## Not yet checked (follow up when time permits)

- ONT plc (LSE) - TR-1 major shareholding notifications / Annual Report substantial-shareholdings table not yet located for a specific G42 filing (see register confirmed_by note on ONT-EQ-2020-Tranche1 for prior findings).
