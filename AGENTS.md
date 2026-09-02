# Working standard for IM_Platform

This platform reports figures that go to management. The governing rule is that **every number
must be traceable to a primary source document**. Nothing is estimated, interpolated or inferred
to fill a gap. A value that cannot be evidenced is shown as pending or unknown.

---

## 1. Document intake is mandatory

**No document enters any analysis until it has been screened.** Not one. Reading a new PDF and
using the number straight away is how wrong figures reach a dashboard.

Whenever new information arrives, run the pipeline in `scripts/evidence_audit/`:

```powershell
.\.venv\Scripts\python.exe -m scripts.evidence_audit.manifest --scan
.\.venv\Scripts\python.exe -m scripts.evidence_audit.backfill_hashes --run
.\.venv\Scripts\python.exe -m scripts.evidence_audit.coverage --export
.\.venv\Scripts\python.exe -m scripts.evidence_audit.bm25 --build
```

Every stage is resumable and safe to re-run.

### Run it when

- month-end or quarter-end reporting lands
- a fund statement, capital account, NAV or board report arrives
- a new deal or legal folder appears
- before certifying a month or refreshing the dashboard

### Before scanning

**Confirm OneDrive is running.** If it is not, cloud placeholders fail to hydrate with
`errno 22` and an entire folder reads as empty. On 2026-09-02 this hid 3,039 files â€” 84% of the
monthly reporting root. A scan that starts with the sync client down must fail loudly, never
report a small corpus.

---

## 2. Provenance rules

- **SHA-256 is the primary key of a document.** Not its filename, not its path.
- **Filename matching is not provenance.** 46% of the corpus is duplicate copies, so one name can
  match many physical files. Where a match is only by name, label it and do not treat it as
  evidence.
- **Record how every match was made.** `sha256_resolved`, `filename_ambiguous`, `unresolved`.
- **Never collapse these four states:** missing Â· not retrievable Â· unreadable Â· excluded by
  scope. They demand different responses and hiding the difference is how gaps become invisible.
- **Coverage is measured, never asserted.** The existence of an index says nothing about what is
  in it.

---

## 3. Validation rules

These come from a real failure. In August 2026 a column-mapping bug read unrealised gain as fair
value throughout the MGX Co-Invest schedule, overstating xAI exposure by $63.6m. It survived
because the check that should have caught it was circular.

- **Never validate a transform with itself.** Summing parsed rows against a parsed total proves
  nothing when both sides used the same mapping. Checks must span columns, span documents, or
  assert structure independently of content.
- **Assert shape before trusting content.** Prove the column template is complete before reading
  any value from it.
- **Establish the domain of a rule before applying it.** An identity derived from one document
  family will produce false breaks on another. Each extractor family needs its own identity set,
  tested against its own documents.
- **Wire corroboration in.** Where a second independent source exists, compare against it and
  show the result. Where none exists, say so on the face of the output.
- **Trace formulas before calling something a break.** Circular references and orphaned scratch
  cells produce convincing false positives.
- **Check the trading calendar per exchange, never portfolio-wide.** LSE and NASDAQ do not share
  holidays.

---

## 4. Scope and attribution

- Always state which basis a figure is on: total partnership Â· investor allocation Â· direct
  holding Â· derived look-through Â· consolidated across vehicles.
- **Never apply a vehicle-level ownership percentage to underlying investments without labelling
  it derived**, and check first whether investment-specific economics exist.
- Instrument fair values in fund reports are **gross**; a fund's NAV is **net** of incentive
  allocation and fund-level items. The two bases differ materially â€” 3.30% against 3.98% for MGX
  Fund I LP â€” and the difference must be disclosed, not smoothed over.
- Do not merge similarly named companies or SPVs without evidence. Use a canonical ID and an
  alias table.

---

## 5. Databases

| File | Role |
|---|---|
| `data/evidence/audit.sqlite` | truth layer â€” source manifest, hashes, provenance, coverage |
| `data/evidence/bm25.sqlite` | BM25 retrieval index, each chunk carrying its source hash |
| `data/portfolio/portfolio.sqlite` | portfolio facts; fund documents carry SHA-256 |
| `data/legal_kb/legal_kb.sqlite` | legacy knowledge base, built without hashes â€” treat as input |

The knowledge base is never mutated by the audit tooling. Provenance is written alongside it so
it can be rebuilt at any time without touching what was originally ingested.

---

## 6. Architecture

The platform has to stay correct as it grows. These are structural rules, not style preferences,
and each exists because breaking it has already cost us something.

### 6.1 The application renders data, never a pre-rendered artefact

**Never embed a generated export into a live view.** Exports are outputs of the system, not
inputs to it.

The Portfolio tab used to embed `G42_Investments_Portfolio_Dashboard_2026-08-25.html`, a file
generated on 25 August and labelled internally *"As of Jul'26"*. It could not follow the month
selector or the entity scope, and its totals â€” committed 2,999.9, invested 2,160.2, carrying
4,568.3 â€” reconciled to no month in the database. Two panels of the same application reported
different periods without saying so, and a genuine question about a 0.2m difference could not
even be framed, let alone answered.

A figure that cannot be traced to a query is not reportable.

### 6.2 One definition, one place

Every metric is defined once in `im_platform.metrics` and imported. No view computes its own
total. When the definition of capital deployed changes it changes in one file, and every screen
moves together or the build fails.

### 6.3 A view is a pure function of (data, selection)

Selection â€” reporting month, entity scope â€” is resolved by a single helper and flows outward.
`_view_month()` is the only thing that decides which month is displayed; thirteen call sites
consume it. That is why making months selectable was a one-line behavioural change rather than
thirteen separate edits, and why no view can silently disagree with the header.

**A view that ignores the current selection is a defect, not a limitation.**

### 6.4 Provenance travels with the figure

Every view names its own source. The register prints the ingest file, its version and the first
twelve characters of its SHA-256. Where no source is recorded it says so rather than leaving the
reader to assume one exists.

### 6.5 Fail visibly, never silently

No empty catch, no quiet fallback, no default that masks absence. A missing document, an
unhydrated file and an unreadable file are three different states and must remain three different
states all the way to the screen. Silence is the failure mode that costs the most, because it
looks identical to success.

### 6.6 Stores are additive and hash-keyed

Schema changes add columns and tables; they do not repurpose existing ones. Documents are keyed
on SHA-256 so that a renamed or relocated file is still recognised as the same evidence. The
audit database is never rebuilt destructively over a source of truth â€” provenance is written
alongside the legacy knowledge base, not into it.

### 6.7 Long-running processes hold stale code

A Streamlit server hot-reloads the entry script but not imported backend packages. On 2026-09-02
the dashboard raised `AttributeError: 'Exposure' object has no attribute 'capital_account_share'`
purely because the server had been running since the previous afternoon. **Restart the server
after any change under `src/backend/`**, and verify with a fresh headless run
(`streamlit.testing.v1.AppTest`) before concluding that code is broken.

### 6.8 Verify through the same path the user takes

`AppTest` drives the real widgets. Playwright cannot operate Streamlit segmented controls, so a
visual check is not a test. Every structural change is verified by loading the app headlessly and
walking the sections it touches.


Search in this order, and never hand-roll regex over raw text before trying the stack:

1. SQLite â€” the purpose-built, validated tables
2. Curated notes with clause references
3. BM25 (`scripts.evidence_audit.bm25 --query`) for names, clauses, dates, defined terms
4. Vector search for semantic recall
5. Raw text only to confirm a hit already located

A zero-result search for a fact known to exist is an **indexing defect**, not absent evidence.
Plain search text is quoted before it reaches FTS5 â€” hyphens and colons are operators, and
`Strategic Co-Invest` was silently rejected as a syntax error until that was fixed.

If a fact has no home in a database, add it to one. Institutionalise rather than re-derive.
