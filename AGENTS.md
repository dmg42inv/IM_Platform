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
`errno 22` and an entire folder reads as empty. On 2026-09-02 this hid 3,039 files — 84% of the
monthly reporting root. A scan that starts with the sync client down must fail loudly, never
report a small corpus.

---

## 2. Provenance rules

- **SHA-256 is the primary key of a document.** Not its filename, not its path.
- **Filename matching is not provenance.** 46% of the corpus is duplicate copies, so one name can
  match many physical files. Where a match is only by name, label it and do not treat it as
  evidence.
- **Record how every match was made.** `sha256_resolved`, `filename_ambiguous`, `unresolved`.
- **Never collapse these four states:** missing · not retrievable · unreadable · excluded by
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

- Always state which basis a figure is on: total partnership · investor allocation · direct
  holding · derived look-through · consolidated across vehicles.
- **Never apply a vehicle-level ownership percentage to underlying investments without labelling
  it derived**, and check first whether investment-specific economics exist.
- Instrument fair values in fund reports are **gross**; a fund's NAV is **net** of incentive
  allocation and fund-level items. The two bases differ materially — 3.30% against 3.98% for MGX
  Fund I LP — and the difference must be disclosed, not smoothed over.
- Do not merge similarly named companies or SPVs without evidence. Use a canonical ID and an
  alias table.

---

## 5. Databases

| File | Role |
|---|---|
| `data/evidence/audit.sqlite` | truth layer — source manifest, hashes, provenance, coverage |
| `data/evidence/bm25.sqlite` | BM25 retrieval index, each chunk carrying its source hash |
| `data/portfolio/portfolio.sqlite` | portfolio facts; fund documents carry SHA-256 |
| `data/legal_kb/legal_kb.sqlite` | legacy knowledge base, built without hashes — treat as input |

The knowledge base is never mutated by the audit tooling. Provenance is written alongside it so
it can be rebuilt at any time without touching what was originally ingested.

---

## 6. Retrieval

Search in this order, and never hand-roll regex over raw text before trying the stack:

1. SQLite — the purpose-built, validated tables
2. Curated notes with clause references
3. BM25 (`scripts.evidence_audit.bm25 --query`) for names, clauses, dates, defined terms
4. Vector search for semantic recall
5. Raw text only to confirm a hit already located

A zero-result search for a fact known to exist is an **indexing defect**, not absent evidence.
Plain search text is quoted before it reaches FTS5 — hyphens and colons are operators, and
`Strategic Co-Invest` was silently rejected as a syntax error until that was fixed.

If a fact has no home in a database, add it to one. Institutionalise rather than re-derive.
