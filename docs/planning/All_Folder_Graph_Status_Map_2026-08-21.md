# All-Folder Document Graph Status Map - 2026-08-21

This document is a detailed handoff map for any future model or analyst taking over the investment document graph work. It records what has actually been completed, what has only been prepared, what must not be claimed yet, and the intended execution path from here.

## Current Bottom Line

Graph generation for all investment folders is **not complete**.

The all-folder sandbox copy and hash-verification layer **is complete**:

- 27 investment folders covered.
- 3,512 source files found.
- 3,512 files copied into the canonical sandbox.
- 0 copy errors.
- 0 missing files.
- 0 hash mismatches.

The next required layer is individual file reading/extraction. Only after that should full folder-level knowledge graphs be generated and represented as complete.

## Hard Working Rule From User

When generating knowledge graphs, every file in the folder must be considered. Do not rely only on promoted files, key documents, or obvious legal files.

A folder graph is complete only when every file has one explicit status:

- text extracted and reviewed into semantic records;
- workbook parsed and reviewed into semantic records;
- archive expanded or catalogued;
- OCR required;
- unsupported format requiring manual review;
- extraction/read failed with a recorded reason;
- or intentionally excluded with an explicit documented reason.

Copying a file is not the same as reading it. Readiness classification is not the same as extraction. Extraction is not the same as legal interpretation.

## Do Not Touch Live Folders

The live investment folders must remain read-only unless the user explicitly authorizes live-folder changes.

Live source root:

```text
C:\Users\divyesh.mahajan\OneDrive - G42\Desktop\0.1 SPPM ###\1. I N V E S T M E N T S  -  Global (Ex China)
```

Covered live categories:

```text
0. E Q U I T Y
1. F U N D - I N V E S T M E N T
```

All document intelligence, extraction, graphing, generated indexes, and derived artifacts should be written to the sandbox, not to the live source folders.

## Canonical Sandbox Root

Use this root for all-folder work:

```text
C:\Users\divyesh.mahajan\OneDrive - G42\Desktop\0.1 SPPM ###\_RS\AF
```

Short form used in notes:

```text
_RS\AF
```

This root is deliberately short because the first all-folder attempt under a longer path hit Windows path-length failures.

Superseded/incomplete all-folder root:

```text
C:\Users\divyesh.mahajan\OneDrive - G42\Desktop\0.1 SPPM ###\_REORG_SANDBOX\2026-08-21_All_Folders
```

That long-root attempt had 138 path-length-related copy failures and should not be treated as the canonical all-folder coverage result.

## Existing Pilot Sandbox Roots

These older pilot roots contain earlier document-intelligence work for selected companies. They are useful reference points but are not the canonical all-folder root.

```text
C:\Users\divyesh.mahajan\OneDrive - G42\Desktop\0.1 SPPM ###\_REORG_SANDBOX\2026-08-20_AAICO_Pilot\AAICO - Applied AI - Source Review Sandbox
C:\Users\divyesh.mahajan\OneDrive - G42\Desktop\0.1 SPPM ###\_REORG_SANDBOX\2026-08-20_BL\BL_SR
C:\Users\divyesh.mahajan\OneDrive - G42\Desktop\0.1 SPPM ###\_REORG_SANDBOX\2026-08-20_CB\CB_SR
```

Pilot status:

- AAICO already had document-intelligence/DGML-style artifacts from earlier work.
- Beyond Limits had registry, semantic elements, deterministic local hashed embedding index, DGML-like output, and then a missing `lineage_graph.yaml` was created.
- Cerebras had registry, semantic elements, deterministic local hashed embedding index, DGML-like output, and then a missing `lineage_graph.yaml` was created.
- These pilot artifacts were generated against selected/pilot source-review structures, not against the complete canonical `_RS\AF` all-folder copy.

## Codebases Involved

Main platform repo:

```text
C:\Users\divyesh.mahajan\Documents\Projects\IM_Platform
```

Document engine repo:

```text
C:\Users\divyesh.mahajan\Documents\Research\AI_Financing_Wiki\document_engine
```

The IM_Platform repo currently holds the sandbox bootstrap utility and planning/status documentation. The separate document engine contains the graph/retrieval CLI used in the earlier pilots.

Known document engine commands from current session context:

```text
build-registry
build-review-queue
export-dgml
build-embeddings
search
search-index
retrieve
answer
extract-clauses
ocr-document
```

Known document engine behavior:

- Current embeddings are deterministic local hash vectors.
- Embedding method recorded earlier: `local_sha256_token_hash_v1`.
- Embedding dimension recorded earlier: 256.
- These embeddings are retrieval aids, not authoritative semantic understanding.

## New Infrastructure Added In IM_Platform

Script:

```text
scripts/bootstrap_sandbox_coverage.py
```

Purpose:

- Create a short-path sandbox for all live investment folders.
- Recursively copy each source file into an archive reference copy under the sandbox.
- Hash every source file.
- Hash every copied target file.
- Verify count, size, and SHA-256 integrity.
- Create an index/readiness layer per investment folder.

Key behavior:

- Uses Windows long-path prefix internally via `\\?\`.
- Creates a standardized folder layout under each investment sandbox.
- Creates `99_Archive` as the byte-for-byte reference copy area.
- Creates `00_Index\Document_Intelligence` and `00_Index\Document_Intelligence\embeddings` placeholders.
- Writes per-file readiness statuses before true extraction is attempted.

Generated per investment folder:

```text
00_Index\source_copy_verification.json
00_Index\file_readiness_inventory.csv
00_Index\COVERAGE_STATUS.md
00_Index\Document_Intelligence\
00_Index\Document_Intelligence\embeddings\
99_Archive\...
```

Generated at sandbox root:

```text
ALL_FOLDERS_COVERAGE_SUMMARY.json
README_COVERAGE.md
```

Validation already done for the script:

- Python compile check passed.
- VS Code diagnostics reported no relevant errors.
- Full short-root run completed with zero copy errors, missing files, or mismatches.

## Canonical Coverage Result

Root summary file:

```text
_RS\AF\ALL_FOLDERS_COVERAGE_SUMMARY.json
```

Root coverage note:

```text
_RS\AF\README_COVERAGE.md
```

Validated summary:

```text
folders: 27
source_files: 3512
copied_files: 3512
copy_errors: 0
missing: 0
mismatches: 0
zero-error folders: 27
```

## Folder Coverage Table

| Category | Investment folder | Source files | Copied files | Copy errors | Missing | Hash mismatches |
|---|---:|---:|---:|---:|---:|---:|
| 0. E Q U I T Y | AAICO (desktop) | 253 | 253 | 0 | 0 | 0 |
| 0. E Q U I T Y | Beyond Limits | 189 | 189 | 0 | 0 | 0 |
| 0. E Q U I T Y | Cerebras | 190 | 190 | 0 | 0 | 0 |
| 0. E Q U I T Y | DriveNets | 39 | 39 | 0 | 0 | 0 |
| 0. E Q U I T Y | e-space | 22 | 22 | 0 | 0 | 0 |
| 0. E Q U I T Y | Endless (Matt Dalio) and E-line | 37 | 37 | 0 | 0 | 0 |
| 0. E Q U I T Y | EsyaSoft | 82 | 82 | 0 | 0 | 0 |
| 0. E Q U I T Y | Flyr | 275 | 275 | 0 | 0 | 0 |
| 0. E Q U I T Y | Glass Earth | 1 | 1 | 0 | 0 | 0 |
| 0. E Q U I T Y | Heygears | 147 | 147 | 0 | 0 | 0 |
| 0. E Q U I T Y | InstaDeep | 245 | 245 | 0 | 0 | 0 |
| 0. E Q U I T Y | Inveniam | 166 | 166 | 0 | 0 | 0 |
| 0. E Q U I T Y | Jysan Technologies | 243 | 243 | 0 | 0 | 0 |
| 0. E Q U I T Y | Life Biosciences | 331 | 331 | 0 | 0 | 0 |
| 0. E Q U I T Y | Liquid AI | 48 | 48 | 0 | 0 | 0 |
| 0. E Q U I T Y | MenaMobile | 77 | 77 | 0 | 0 | 0 |
| 0. E Q U I T Y | Neuralink (Project Cortex) | 53 | 53 | 0 | 0 | 0 |
| 0. E Q U I T Y | ONT | 194 | 194 | 0 | 0 | 0 |
| 0. E Q U I T Y | School Hack | 9 | 9 | 0 | 0 | 0 |
| 0. E Q U I T Y | TFH - Worldcoin | 76 | 76 | 0 | 0 | 0 |
| 0. E Q U I T Y | Verses (Project Bayes) | 93 | 93 | 0 | 0 | 0 |
| 0. E Q U I T Y | VTVT - vTv Therapeutics | 77 | 77 | 0 | 0 | 0 |
| 1. F U N D - I N V E S T M E N T | 1. New Space Capital Fund | 212 | 212 | 0 | 0 | 0 |
| 1. F U N D - I N V E S T M E N T | 2. North Summit Capital Fund | 293 | 293 | 0 | 0 | 0 |
| 1. F U N D - I N V E S T M E N T | 2. Sinovation Disrupt Fund | 4 | 4 | 0 | 0 | 0 |
| 1. F U N D - I N V E S T M E N T | 3. ACIES | 122 | 122 | 0 | 0 | 0 |
| 1. F U N D - I N V E S T M E N T | 4. MGX | 34 | 34 | 0 | 0 | 0 |

Total: 3,512 files copied and hash-verified.

## Current Graph Artifact Status In Canonical Sandbox

Checked under:

```text
_RS\AF
```

Current result:

```text
Document_Intelligence directories: 27
Graph / embedding artifact files: 0
```

Meaning:

- The canonical all-folder sandbox has all 27 `Document_Intelligence` directories prepared.
- It does not yet contain `dgml_like.xml`, `lineage_graph.yaml`, `.dgml`, `.graphml`, or `semantic_elements_index.json` files.
- Therefore, all-folder graph generation has not been run in the canonical sandbox.

Do not say: "all folder graphs are complete."

Correct statement: "all folder source files are copied and hash-verified; graph generation remains pending behind the read/extraction layer."

## Readiness Layer Already Available

Each `file_readiness_inventory.csv` has one row per source file and assigns a preliminary content-readiness bucket based on extension.

Known readiness statuses from the script:

- `text_readable_pending_parse`
- `pdf_text_or_ocr_required`
- `office_parser_required`
- `ocr_required`
- `archive_expansion_required`
- `binary_or_unknown_review_required`

These are useful routing labels, but they are not extraction results. They say what kind of parser or review is likely required.

Example from AAICO readiness counts:

- `pdf_text_or_ocr_required`: 114
- `office_parser_required`: 104
- `archive_expansion_required`: 15
- `text_readable_pending_parse`: 7
- `ocr_required`: 7
- `binary_or_unknown_review_required`: 6

## What Was Done Earlier In This Session

Dashboard work:

- Modified `src/backend/im_platform/adapters/tracker_style_dashboard.py`.
- Added per-column dropdown filters to generated dashboard tables.
- Filters apply independently per table and use AND logic across active column filters.
- Hidden rows are excluded from CSV download.
- Validated in browser with Playwright: Live table had 13 dropdowns and the Status filter worked across holding-company sections.
- Regenerated `data/outputs/Tracker_Style_Dashboard.html`.
- Ran unit tests: `pytest tests/unit -q` passed with 3 tests.

Document pilot work:

- Resumed AAICO/Beyond Limits/Cerebras document-intelligence work.
- Verified BL and Cerebras had DGML-like files and deterministic hashed embedding indexes in their older pilot sandboxes.
- Created missing BL and Cerebras `lineage_graph.yaml` files in older pilot sandbox locations.
- Ran/checked Q&A for Beyond Limits and Cerebras against the pilot artifacts.
- Preserved key BL caveat: legal schedule candidate showed a USD 100m commitment while platform paid-in was USD 90m; final approximately USD 10m appears not funded/cancelled and must not be silently treated as paid-in.
- Preserved key Cerebras caveat: approximately USD 335m-350m later opportunity / Project Circuit-style transaction did not proceed due to CFIUS-related issues and must not be presented as invested/paid-in capital or as the original Series F.

All-folder infrastructure work:

- Created `scripts/bootstrap_sandbox_coverage.py`.
- First all-folder copy attempt under the longer `_REORG_SANDBOX\2026-08-21_All_Folders` path hit Windows path-length failures.
- Confirmed source files themselves were accessible by probing a failing ONT file to a shorter target.
- Switched to the shorter canonical `_RS\AF` root.
- Re-ran all-folder coverage successfully with zero errors/missing/mismatches.
- Created `_RS\AF\README_COVERAGE.md` documenting the root and interpretation.

## Important Business/Source Caveats To Preserve

Beyond Limits:

- There is a known distinction between a USD 100m legal commitment/schedule candidate and approximately USD 90m platform paid-in.
- Do not represent the full USD 100m as paid-in unless source evidence supports it.
- The apparent final approximately USD 10m was not funded/cancelled based on current understanding.

Cerebras:

- Original Series F platform paid-in is approximately USD 40m, plus small later warrant-exercise amounts if applicable in the tracker context.
- A later approximately USD 335m-350m opportunity / Project Circuit-style transaction did not proceed due to CFIUS-related issues.
- Do not fold that later opportunity into paid-in capital.
- Do not present that later opportunity as the original 2021 Series F.

Dashboard/tracker context:

- Dashboard filtering is complete and validated.
- This is separate from document graph completion.
- Do not confuse portfolio tracker reconciliation status with document graph read coverage.

## What Must Happen Next

The immediate next engineering task is to build the extraction/read coverage layer over `_RS\AF`.

Recommended first target:

```text
_RS\AF\0_E_Q_U_I_T_Y\ONT\SR
```

Reason ONT is a good first full-folder graph target:

- It has enough file volume to test the process seriously: 194 files.
- It likely has layered legal, funding, tranche, corporate-action, monitoring, and public/filing-style materials.
- It is complex enough to expose parser and graph-model weaknesses before running all 27 folders.

Recommended next target order after ONT:

1. DriveNets.
2. Inveniam.
3. Remaining equity folders by file count/risk.
4. Fund folders after the equity extraction pattern is stable.

## Required Extraction Outputs Per Folder

For each folder, create or update these outputs under `00_Index\Document_Intelligence`:

```text
extraction_manifest.json
extraction_status.csv
semantic_elements.jsonl
semantic_elements_index.json
review_queue.csv
lineage_graph.yaml
dgml_like.xml
embeddings\semantic_elements_index.json
QA_CHECKS.md
GRAPH_STATUS.md
```

The exact names can be adjusted to match the document engine's existing conventions, but the concepts should remain separate:

- file-level extraction status;
- semantic/knowledge records;
- graph edges/nodes;
- embedding/retrieval index;
- human review queue;
- Q&A validation log;
- final folder graph status.

## Extraction Pipeline Requirements

Minimum parser requirements:

- Plain text/Markdown/CSV/JSON/YAML/HTML: direct read and normalized text capture.
- PDF: text extraction first; if text is empty/low-quality, mark OCR required.
- DOCX: extract paragraphs, tables, headers/footers if possible.
- XLSX: extract workbook metadata, sheet names, used ranges, cell text/values, and table-like areas.
- PPTX: extract slide text, speaker notes if available, and slide-level metadata.
- MSG/email files: parse if tooling exists; otherwise mark manual review/parser required.
- Images/TIFF scans: OCR required unless an OCR tool is configured.
- ZIP/7z/RAR archives: expand or catalogue; contained files must not be ignored.
- Unknown/binary: manual classification required.

Minimum extraction-status fields:

- original relative path;
- archive path;
- SHA-256;
- file extension;
- size;
- parser selected;
- extraction status;
- extracted character count;
- page/sheet/slide count where available;
- OCR required flag;
- manual review required flag;
- error message if failed;
- generated semantic element count;
- reviewer notes.

## Graph Completion Criteria Per Folder

A folder can be called graph-complete only when all of the following are true:

- Every file from `file_readiness_inventory.csv` appears in `extraction_status.csv`.
- Every file has a terminal extraction/review status.
- Every extracted/read file contributes either semantic elements or an explicit "no relevant content" record.
- Every blocked file is listed in a review queue with a reason.
- The folder has a generated graph artifact, such as `lineage_graph.yaml` and/or `dgml_like.xml`.
- The folder has a retrieval/embedding index if Q&A is expected.
- At least a small Q&A smoke test is recorded in `QA_CHECKS.md`.
- `GRAPH_STATUS.md` explicitly states remaining limitations.

## All-Folder Completion Criteria

The all-folder graph effort is complete only when:

- All 27 folders meet the folder-level graph completion criteria.
- The aggregate all-folder summary reports 3,512 files as extracted/read, blocked, OCR-required, manual-review-required, or explicitly no-content.
- No copied file is silently omitted from extraction status.
- Any OCR/manual-review backlog is counted and visible.
- Aggregate graph artifact counts match the 27-folder scope.
- Cross-folder Q&A can identify which folder/file supports each answer.

## Recommended Next Implementation Step

Create a new extraction coverage script in the IM_Platform repo, likely:

```text
scripts/build_extraction_coverage.py
```

Initial scope:

- Read one folder's `00_Index\file_readiness_inventory.csv`.
- Process files under that folder's `99_Archive`.
- Implement direct text extraction for plain-text-like files.
- Implement PDF text extraction using an available installed library if present.
- Implement DOCX/XLSX/PPTX extraction if dependencies are already present or can be safely added.
- Classify unsupported files without crashing.
- Write `extraction_status.csv` and `extraction_manifest.json`.
- Run first on ONT only.

After ONT extraction coverage is validated, connect the extracted content into the document engine's graph/embedding generation flow.

## Commands And Checks That Were Useful

Activate IM_Platform venv:

```powershell
(Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned) ; (& c:\Users\divyesh.mahajan\Documents\Projects\IM_Platform\.venv\Scripts\Activate.ps1)
```

Summarize all-folder copy coverage:

```powershell
$p = 'C:\Users\divyesh.mahajan\OneDrive - G42\Desktop\0.1 SPPM ###\_RS\AF\ALL_FOLDERS_COVERAGE_SUMMARY.json'
$data = Get-Content -Raw $p | ConvertFrom-Json
Write-Output ('folders ' + $data.Count)
Write-Output ('source_files ' + (($data | Measure-Object -Property source_file_count -Sum).Sum))
Write-Output ('copied_files ' + (($data | Measure-Object -Property copied_file_count -Sum).Sum))
Write-Output ('copy_errors ' + (($data | Measure-Object -Property copy_error_count -Sum).Sum))
Write-Output ('missing ' + (($data | Measure-Object -Property missing_count -Sum).Sum))
Write-Output ('mismatches ' + (($data | Measure-Object -Property mismatch_count -Sum).Sum))
```

Check whether canonical sandbox graph artifacts exist:

```powershell
$root = 'C:\Users\divyesh.mahajan\OneDrive - G42\Desktop\0.1 SPPM ###\_RS\AF'
$di = Get-ChildItem -Path $root -Recurse -Directory -Filter 'Document_Intelligence'
$graphFiles = Get-ChildItem -Path $root -Recurse -File | Where-Object { $_.Name -in @('dgml_like.xml','lineage_graph.yaml','semantic_elements_index.json') -or $_.Extension -in @('.dgml','.graphml') }
Write-Output ('document_intelligence_dirs ' + $di.Count)
Write-Output ('graph_or_embedding_files ' + $graphFiles.Count)
```

Observed result:

```text
document_intelligence_dirs 27
graph_or_embedding_files 0
```

## Known Tooling/Environment Notes

- PowerShell inline Python and very long OneDrive paths with spaces/special characters can be brittle. Prefer short sandbox paths and/or small repo scripts over complex inline commands.
- Use the short canonical `_RS\AF` sandbox to avoid path-length failures.
- PyYAML was not installed in the IM_Platform virtual environment during the pilot graph checks, so YAML validation was file-existence/manual unless a parser is installed.
- Do not install new dependencies casually without checking the repo style and whether they are really needed.
- For IM_Platform code changes, run `pytest tests/unit -q` after edits.

## Current Recommended Answer To User If Asked "Are We Done?"

No. We are done with all-folder copy/hash coverage, but not all-folder graph generation.

Precise answer:

```text
All 27 live/exited investment folders have been copied into the canonical short-root sandbox and hash-verified: 3,512/3,512 files, zero missing, zero mismatches. The canonical sandbox has 27 Document_Intelligence directories but zero generated graph/embedding artifacts. The next step is extraction/read coverage per file, then graph generation folder by folder.
```

## Immediate Next Action

Start ONT extraction coverage:

```text
_RS\AF\0_E_Q_U_I_T_Y\ONT\SR
```

Do not jump straight to graph generation until ONT's 194 files are all represented in an extraction/read-status artifact.
