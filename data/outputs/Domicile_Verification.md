# Domicile Verification Worksheet

Generated 2026-08-25. Each grounded domicile candidate checked against its cited document in the legal knowledge base (legal_kb.sqlite). The cited phrase being present is necessary but NOT sufficient - we also check the matched sentence names the company itself (self_named) rather than an auditor / law firm / template placeholder.

## Summary

- **high** confidence (phrase verbatim AND names the company): **2**
- **medium** confidence (phrase/term found, context unclear): **5**
- **low** confidence (matched a third party / placeholder - REVIEW): **4**

Phrase-match tally: phrase_verified=10, term_only=1, phrase_not_found=0, doc_not_found=0.

Only **high** rows are safe to promote to domicile_status=confirmed on a glance. **low** rows are likely false positives (the phrase describes someone else).

| Confidence | Company | Domicile | Quality | Evidence (from cited doc) | Source file |
|---|---|---|---|---|---|
| high | beyond limits | Delaware | self_named | ellect Inc. (f/k/a Beyond Limits Media Group, Inc.) ("BII") - BII was incorporated in the State of Delaware, USA on November 12, 2014 with registra... | Project Emerald - DD Report.pdf |
| high | flyr inc | Delaware | self_named | common stock as collateral. In March 2022, FLYR Labs Global, Inc. was incorporated in Delaware for the purpose of hiring international employees. F... | FLYR, Inc. and Subsidiaries FS 12 31 21.pdf |
| medium | e-line ventures llc | Delaware | context_unclear | 2.1. Formation. The Company has been organized as a Delaware limited liability company by the filing of a certificate of formation | Round 1, Endless Studios Limited Liability Company Agreement.pdf |
| medium | inveniam ltd | Abu Dhabi Global Market (ADGM) | context_unclear | relates. "Group 42 Holding" means Group 42 Holding Limited, a company registered in the Abu Dhabi Global Market with company number 000001430 and w... | G42 x PGIM - NDA 20.11.2024 v1.docx |
| medium | north summit capital fund | China | context_unclear | t on the foregoing pro rata basis with respect to a portfolio company organized under PRC law if such portfolio company (A) is not a suitable inves... | 1. North Summit Capital Fund - Amended and.PDF |
| medium | verses ai inc | California | context_unclear | and (3) intangible personal property if the corporation's commercial domicile is in California or the income is otherwise allocable to California. ... | Verses Technologies USA Inc & Subs - FYE 3.31.22 CA Return.pdf |
| medium | school hack (airev holding limited) | Abu Dhabi Global Market (ADGM) | context_unclear | SPV RSC LTD (company number 16508 incorporated under the laws of the Abu Dhabi Global Market) whose registered office is at 2458, 24, Al Sila Tower... | 9e._Schoolhack_-_Shareholders'_Agreement_-_Execution_Version.pdf |
| low | mgx 1 strategic co-invest | Abu Dhabi Global Market (ADGM) | third_party_context | 6456610, www.pwc.com/me PricewaterhouseCoopers Limited Partnership is registered in the Abu Dhabi Global Market 5 Independent auditor's report to t... | MGX Strategic Co-invest LP - Audited Financial Statement - 2024_GX Investments Ltd.pdf |
| low | mgx group holding 1 ltd (gp) | Abu Dhabi Global Market (ADGM) | third_party_context | 6456610, www.pwc.com/me PricewaterhouseCoopers Limited Partnership is registered in the Abu Dhabi Global Market 5 Independent auditor's report to t... | MGX Strategic Co-invest LP - Audited Financial Statement - 2024_GX Investments Ltd.pdf |
| low | mgx i denali holding lp | Abu Dhabi Global Market (ADGM) | third_party_context | 6456610, www.pwc.com/me PricewaterhouseCoopers Limited Partnership is registered in the Abu Dhabi Global Market 5 Independent auditor's report to t... | MGX Strategic Co-invest LP - Audited Financial Statement - 2024_GX Investments Ltd.pdf |
| low | mgx i lp | Abu Dhabi Global Market (ADGM) | third_party_context | 6456610, www.pwc.com/me PricewaterhouseCoopers Limited Partnership is registered in the Abu Dhabi Global Market 5 Independent auditor's report to t... | MGX Strategic Co-invest LP - Audited Financial Statement - 2024_GX Investments Ltd.pdf |