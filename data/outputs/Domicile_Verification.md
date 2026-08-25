# Domicile Verification Worksheet

Generated 2026-08-25. Each grounded domicile candidate checked against its cited document in the legal knowledge base (legal_kb.sqlite). The cited phrase being present is necessary but NOT sufficient - we also check the matched sentence names the company itself (self_named) rather than an auditor / law firm / template placeholder.

## Summary

- **high** confidence (phrase verbatim AND names the company): **2**
- **medium** confidence (phrase/term found, context unclear): **14**
- **low** confidence (matched a third party / placeholder - REVIEW): **8**

Phrase-match tally: phrase_verified=23, term_only=1, phrase_not_found=0, doc_not_found=0.

Only **high** rows are safe to promote to domicile_status=confirmed on a glance. **low** rows are likely false positives (the phrase describes someone else).

| Confidence | Company | Domicile | Quality | Evidence (from cited doc) | Source file |
|---|---|---|---|---|---|
| high | beyond limits | Delaware | self_named | ellect Inc. (f/k/a Beyond Limits Media Group, Inc.) ("BII") - BII was incorporated in the State of Delaware, USA on November 12, 2014 with registra... | Project Emerald - DD Report.pdf |
| high | flyr inc | Delaware | self_named | common stock as collateral. In March 2022, FLYR Labs Global, Inc. was incorporated in Delaware for the purpose of hiring international employees. F... | FLYR, Inc. and Subsidiaries FS 12 31 21.pdf |
| medium | drivenets | Israel | context_unclear | ualification. The Company is a corporation duly organized and validly existing under the laws of the State of Israel and has all requisite corporat... | DriveNets - Series D - SPA [Meitar April 16, 2026](14938774.23).docx |
| medium | e-line ventures llc | Delaware | context_unclear | 2.1. Formation. The Company has been organized as a Delaware limited liability company by the filing of a certificate of formation | Round 1, Endless Studios Limited Liability Company Agreement.pdf |
| medium | endless studios llc | Delaware | context_unclear | 2.1. Formation. The Company has been organized as a Delaware limited liability company by the filing of a certificate of formation | Round 1, Endless Studios Limited Liability Company Agreement.pdf |
| medium | esyasoft holding | Dubai International Financial Centre (DIFC) | context_unclear | aSoft " or the "Company"), is a private company limited by shares and incorporated under the laws of Dubai International Financial Centre, having i... | G42 Esyasoft Due Diligence Report 2 4 20.docx |
| medium | instadeep limited | England and Wales | context_unclear | neral information The company is a private company limited by shares, registered in England and Wales. The address of the registered office is 2 Ea... | 2. UK - 2019 FINAL_full_accts_ye_311219 (11) (1).pdf |
| medium | inveniam ltd | Abu Dhabi Global Market (ADGM) | context_unclear | relates. "Group 42 Holding" means Group 42 Holding Limited, a company registered in the Abu Dhabi Global Market with company number 000001430 and w... | G42 x PGIM - NDA 20.11.2024 v1.docx |
| medium | liquid ai | Delaware | context_unclear | oposed to be taken is delivered to the Corporation by delivery to its registered office in the State of Delaware, its principal office, or an offic... | Liquid AI, Inc. - Series A - Secretary's Certificate [EXECUTED].pdf |
| medium | mena mobile inc | Cayman Islands | context_unclear | nd of financing if the registration is completed then. The Target was incorporated in the Cayman Islands on August 22, 2016. The share capital of t... | Mena Mobile - Due Diligence Report (final).pdf |
| medium | neuralink | Nevada | context_unclear | Agreement (the "SPA"). Company Snapshot The Company is a corporation incorporated in Nevada. The principal executive office of the Company is locat... | Neuralink Investment Summary .docx |
| medium | north summit capital fund | China | context_unclear | t on the foregoing pro rata basis with respect to a portfolio company organized under PRC law if such portfolio company (A) is not a suitable inves... | 1. North Summit Capital Fund - Amended and.PDF |
| medium | ont plc | United Kingdom | context_unclear | General Information Oxford Nanopore Technologies Limited is a company incorporated in the United Kingdom under the Companies Act 2006 and is regist... | 31-12-2019 ONT Accounts.pdf |
| medium | sinovation disrupt fund, l.p. | Cayman Islands | context_unclear | ip Interests. The General Partner shall cause to be maintained at the registered office of the Partnership in the Cayman Islands or such other plac... | Amended and Restated LPA 12.pdf |
| medium | verses ai inc | California | context_unclear | and (3) intangible personal property if the corporation's commercial domicile is in California or the income is otherwise allocable to California. ... | Verses Technologies USA Inc & Subs - FYE 3.31.22 CA Return.pdf |
| medium | school hack (airev holding limited) | Abu Dhabi Global Market (ADGM) | context_unclear | SPV RSC LTD (company number 16508 incorporated under the laws of the Abu Dhabi Global Market) whose registered office is at 2458, 24, Al Sila Tower... | 9e._Schoolhack_-_Shareholders'_Agreement_-_Execution_Version.pdf |
| low | jysan technologies | England and Wales | template_placeholder | f adherence This deed is dated [DATE] Parties (1) [FULL COMPANY NAME] incorporated and registered in England and Wales with company number [NUMBER]... | 2. JYSAN - Shareholders' Agreement - Executed Version.pdf |
| low | mgx 1 strategic co-invest | Abu Dhabi Global Market (ADGM) | third_party_context | 6456610, www.pwc.com/me PricewaterhouseCoopers Limited Partnership is registered in the Abu Dhabi Global Market 5 Independent auditor's report to t... | MGX Strategic Co-invest LP - Audited Financial Statement - 2024_GX Investments Ltd.pdf |
| low | mgx group holding 1 ltd (gp) | Abu Dhabi Global Market (ADGM) | third_party_context | 6456610, www.pwc.com/me PricewaterhouseCoopers Limited Partnership is registered in the Abu Dhabi Global Market 5 Independent auditor's report to t... | MGX Strategic Co-invest LP - Audited Financial Statement - 2024_GX Investments Ltd.pdf |
| low | mgx i denali holding lp | Abu Dhabi Global Market (ADGM) | third_party_context | 6456610, www.pwc.com/me PricewaterhouseCoopers Limited Partnership is registered in the Abu Dhabi Global Market 5 Independent auditor's report to t... | MGX Strategic Co-invest LP - Audited Financial Statement - 2024_GX Investments Ltd.pdf |
| low | mgx i lp | Abu Dhabi Global Market (ADGM) | third_party_context | 6456610, www.pwc.com/me PricewaterhouseCoopers Limited Partnership is registered in the Abu Dhabi Global Market 5 Independent auditor's report to t... | MGX Strategic Co-invest LP - Audited Financial Statement - 2024_GX Investments Ltd.pdf |
| low | new space capital fund i | Luxembourg | third_party_context | 0M2409102200581<241 L<<<42 Arendt & Medernach SA L-2082 Luxembourg Registered with the Luxembourg Bar RCS Luxembourg B 186371 I VAT Lu2eaRa704 YZ T... | Passport certified copy KARAVAEV.pdf |
| low | new space capital gp com scsp | Luxembourg | third_party_context | 0M2409102200581<241 L<<<42 Arendt & Medernach SA L-2082 Luxembourg Registered with the Luxembourg Bar RCS Luxembourg B 186371 I VAT Lu2eaRa704 YZ T... | Passport certified copy KARAVAEV.pdf |
| low | vtv therapeutics inc. | Delaware | third_party_context | 18, a New York trust (the "ROP Revocable Trust"), MacAndrews & Forbes Incorporated, a Delaware corporation ("MacAndrews & Forbes"), MacAndrews & Fo... | AGM Notice May 2025.pdf |