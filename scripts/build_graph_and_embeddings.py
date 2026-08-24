"""Build a full-folder DGML-style graph and a queryable vector index.

Step 3+4 of the pipeline (after extraction). Consumes the extracted text and
extraction_status.csv produced by build_extraction_coverage.py and produces, in
the sandbox's 00_Index/Document_Intelligence folder:

    document_registry.json   - every file as a node (incl. blocked ones)
    dgml_like.xml            - DGML-style document set + structural relationships
    embeddings/passage_index.json - chunked, real-text vector index (queryable)
    graph_manifest.json      - counts and provenance
    GRAPH_STATUS.md          - human-readable completion status

Unlike the earlier curated pilots (which promoted ~a dozen key files), this
represents EVERY file in the folder, so no file is silently excluded.

Embedding model: deterministic, offline, local signed hashing vectorizer
(`local_sha256_signed_hash_v1`, 256 dims). It is a retrieval aid, not an
authoritative semantic model.

Usage:
    # build graph + index for a folder
    python scripts/build_graph_and_embeddings.py --folder "<...>/ONT/SR"

    # query the built index
    python scripts/build_graph_and_embeddings.py --folder "<...>/ONT/SR" --query "term sheet valuation" --top-k 8
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from xml.dom import minidom

EMBEDDING_MODEL = "local_sha256_signed_hash_v1"
DIMENSIONS = 256
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150
TOKEN_RE = re.compile(r"[A-Za-z0-9$%.]+")

# Filename / folder keyword -> document_type (structural inference only).
DOC_TYPE_RULES = [
    ("term sheet", "term_sheet"),
    ("cap table", "cap_table"),
    ("captable", "cap_table"),
    ("subscription", "subscription_agreement"),
    ("share purchase", "share_purchase_agreement"),
    ("stock purchase", "stock_purchase_agreement"),
    ("purchase agreement", "purchase_agreement"),
    ("shareholders agreement", "shareholders_agreement"),
    ("shareholder resolution", "shareholder_resolution"),
    ("board resolution", "board_resolution"),
    ("resolution", "resolution"),
    ("investors rights", "investors_rights_agreement"),
    ("side letter", "side_letter"),
    ("warrant", "warrant"),
    ("convertible", "convertible_instrument"),
    ("charter", "charter"),
    ("certificate of incorporation", "charter"),
    ("articles", "constitutional_document"),
    ("valuation", "valuation_support"),
    ("financial", "financial_statement"),
    ("audited", "financial_statement"),
    ("investor model", "financial_model"),
    ("cashflow", "financial_model"),
    ("due diligence", "due_diligence"),
    ("dd ", "due_diligence"),
    ("memo", "investment_memo"),
    ("investment note", "investment_note"),
    ("prospectus", "public_filing"),
    ("s-1", "public_filing"),
    ("closing", "closing_document"),
]


def long_path(path: Path) -> str:
    resolved = str(path.resolve(strict=False))
    if resolved.startswith("\\\\?\\"):
        return resolved
    return "\\\\?\\" + resolved


def slugify(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return slug or "item"


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def embed(text: str) -> list[float]:
    """Deterministic signed hashing vectorizer, L2-normalised."""
    vec = [0.0] * DIMENSIONS
    for token in tokenize(text):
        digest = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
        index = digest % DIMENSIONS
        sign = 1.0 if (digest >> 8) & 1 else -1.0
        vec[index] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def chunk_text(text: str) -> list[tuple[int, str]]:
    text = text.strip()
    if not text:
        return []
    out: list[tuple[int, str]] = []
    step = max(1, CHUNK_SIZE - CHUNK_OVERLAP)
    index = 0
    while index < len(text):
        piece = text[index:index + CHUNK_SIZE]
        if piece.strip():
            out.append((index, piece))
        index += step
    return out


def infer_document_type(relative_path: str) -> str:
    lowered = relative_path.lower()
    for keyword, doc_type in DOC_TYPE_RULES:
        if keyword in lowered:
            return doc_type
    return "unclassified_document"


def matter_folder(relative_path: str) -> str:
    """First path segment = the 'matter'/topic grouping for structural edges."""
    parts = Path(relative_path).parts
    return parts[0] if parts else ""


@dataclass
class DocNode:
    document_id: str
    relative_path: str
    filename: str
    extension: str
    document_type: str
    matter_folder: str
    extraction_status: str
    char_count: int
    parser: str
    graph_role: str
    note: str = ""


def load_extraction_rows(intel_root: Path) -> list[dict[str, str]]:
    status_csv = intel_root / "extraction_status.csv"
    if not status_csv.exists():
        raise FileNotFoundError(f"Missing extraction_status.csv: {status_csv}. Run build_extraction_coverage.py first.")
    with status_csv.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build(folder: Path) -> dict[str, object]:
    intel_root = folder / "00_Index" / "Document_Intelligence"
    text_root = intel_root / "extracted_text"
    emb_root = intel_root / "embeddings"
    os.makedirs(long_path(emb_root), exist_ok=True)

    rows = load_extraction_rows(intel_root)
    transaction_id = slugify(folder.parent.name)

    nodes: list[DocNode] = []
    passages: list[dict[str, object]] = []
    seen_ids: set[str] = set()

    for row in rows:
        relative = row["relative_path"]
        status = row.get("status", "")
        base_id = slugify(relative)
        document_id = base_id
        suffix = 2
        while document_id in seen_ids:
            document_id = f"{base_id}_{suffix}"
            suffix += 1
        seen_ids.add(document_id)

        char_count = int(row.get("char_count") or 0)
        readable = status == "extracted_text"
        node = DocNode(
            document_id=document_id,
            relative_path=relative,
            filename=Path(relative).name,
            extension=(row.get("extension") or Path(relative).suffix).lower(),
            document_type=infer_document_type(relative),
            matter_folder=matter_folder(relative),
            extraction_status=status,
            char_count=char_count,
            parser=row.get("parser", ""),
            graph_role="text_node" if readable else "blocked_node",
            note=row.get("note", ""),
        )
        nodes.append(node)

        if not readable:
            continue
        text_file = text_root / (relative + ".txt")
        if not os.path.exists(long_path(text_file)):
            node.graph_role = "blocked_node"
            node.note = "Marked extracted_text but text file missing."
            continue
        with open(long_path(text_file), "r", encoding="utf-8", errors="replace") as handle:
            content = handle.read()
        for start, piece in chunk_text(content):
            passages.append({
                "passage_id": f"{document_id}::{start}",
                "document_id": document_id,
                "relative_path": relative,
                "document_type": node.document_type,
                "matter_folder": node.matter_folder,
                "char_start": start,
                "char_end": start + len(piece),
                "text": piece,
                "vector": embed(piece),
            })

    _write_registry(intel_root, transaction_id, folder, nodes)
    _write_dgml(intel_root, transaction_id, folder, nodes)
    manifest = _write_embeddings(emb_root, transaction_id, passages, nodes)
    _write_graph_status(intel_root, transaction_id, folder, nodes, passages)
    return manifest


def _write_registry(intel_root: Path, transaction_id: str, folder: Path, nodes: list[DocNode]) -> None:
    registry = {
        "transaction_id": transaction_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sandbox_root": str(folder),
        "file_count": len(nodes),
        "text_node_count": sum(1 for n in nodes if n.graph_role == "text_node"),
        "blocked_node_count": sum(1 for n in nodes if n.graph_role == "blocked_node"),
        "files": [asdict(n) for n in nodes],
    }
    with open(long_path(intel_root / "document_registry.json"), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(registry, indent=2))


def _write_dgml(intel_root: Path, transaction_id: str, folder: Path, nodes: list[DocNode]) -> None:
    doc = minidom.Document()
    root = doc.createElementNS("https://dgml.io/ns", "dg:DocumentSet")
    root.setAttribute("xmlns:dg", "https://dgml.io/ns")
    root.setAttribute("transactionId", transaction_id)
    root.setAttribute("name", folder.parent.name)
    root.setAttribute("rootStrategy", "full_folder_extraction_coverage")
    doc.appendChild(root)

    for node in nodes:
        element = doc.createElement("dg:Document")
        element.setAttribute("documentId", node.document_id)
        element.setAttribute("title", node.filename)
        element.setAttribute("type", node.document_type)
        element.setAttribute("matterFolder", node.matter_folder)
        element.setAttribute("extractionStatus", node.extraction_status)
        element.setAttribute("graphRole", node.graph_role)
        element.setAttribute("path", "../../99_Archive/" + node.relative_path.replace("\\", "/"))
        root.appendChild(element)

    # Structural relationships: files sharing a top-level matter folder.
    rel_root = doc.createElement("dg:Relationships")
    root.appendChild(rel_root)
    by_matter: dict[str, list[DocNode]] = {}
    for node in nodes:
        by_matter.setdefault(node.matter_folder, []).append(node)
    for matter, group in sorted(by_matter.items()):
        if len(group) < 2:
            continue
        rel = doc.createElement("dg:MatterGroup")
        rel.setAttribute("matterFolder", matter)
        rel.setAttribute("documentCount", str(len(group)))
        for node in group:
            member = doc.createElement("dg:Member")
            member.setAttribute("documentId", node.document_id)
            rel.appendChild(member)
        rel_root.appendChild(rel)

    xml_bytes = doc.toprettyxml(indent="  ", encoding="utf-8")
    with open(long_path(intel_root / "dgml_like.xml"), "wb") as handle:
        handle.write(xml_bytes)


def _write_embeddings(emb_root: Path, transaction_id: str, passages: list[dict[str, object]], nodes: list[DocNode]) -> dict[str, object]:
    index = {
        "index_type": "chunked_signed_hash_bag_of_terms",
        "embedding_model": EMBEDDING_MODEL,
        "dimensions": DIMENSIONS,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "transaction_id": transaction_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "passage_count": len(passages),
        "documents_with_passages": len({p["document_id"] for p in passages}),
        "passages": passages,
    }
    with open(long_path(emb_root / "passage_index.json"), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(index, indent=2))

    manifest = {
        "transaction_id": transaction_id,
        "generated_at_utc": index["generated_at_utc"],
        "embedding_model": EMBEDDING_MODEL,
        "dimensions": DIMENSIONS,
        "file_count": len(nodes),
        "text_node_count": sum(1 for n in nodes if n.graph_role == "text_node"),
        "blocked_node_count": sum(1 for n in nodes if n.graph_role == "blocked_node"),
        "passage_count": len(passages),
        "documents_with_passages": index["documents_with_passages"],
    }
    with open(long_path(emb_root.parent / "graph_manifest.json"), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(manifest, indent=2))
    return manifest


def _write_graph_status(intel_root: Path, transaction_id: str, folder: Path, nodes: list[DocNode], passages: list[dict[str, object]]) -> None:
    blocked = [n for n in nodes if n.graph_role == "blocked_node"]
    lines = [
        f"# Graph Status - {folder.parent.name}",
        "",
        f"- Transaction id: {transaction_id}",
        f"- Files represented as nodes: {len(nodes)}",
        f"- Text nodes (embedded): {len(nodes) - len(blocked)}",
        f"- Blocked nodes (no text): {len(blocked)}",
        f"- Passages in vector index: {len(passages)}",
        "",
        "## Blocked nodes (still not graph-readable)",
        "",
    ]
    if blocked:
        for node in blocked:
            lines.append(f"- [{node.extraction_status}] {node.relative_path} :: {node.note}")
    else:
        lines.append("- None. Every file contributed text to the graph.")
    lines.extend([
        "",
        "## Interpretation",
        "",
        "Every file in extraction_status.csv is a node in document_registry.json and dgml_like.xml.",
        "Text nodes are chunked and embedded in embeddings/passage_index.json and are queryable.",
        "Blocked nodes are represented but carry no text; resolve them (convert/OCR/manual) for full coverage.",
        "Embeddings are a deterministic offline retrieval aid, not an authoritative semantic model.",
    ])
    with open(long_path(intel_root / "GRAPH_STATUS.md"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def query(folder: Path, question: str, top_k: int) -> list[dict[str, object]]:
    emb_index = folder / "00_Index" / "Document_Intelligence" / "embeddings" / "passage_index.json"
    if not emb_index.exists():
        raise FileNotFoundError(f"Missing passage index: {emb_index}. Build it first.")
    with open(long_path(emb_index), "r", encoding="utf-8") as handle:
        index = json.load(handle)
    query_vec = embed(question)
    scored = []
    for passage in index["passages"]:
        score = cosine(query_vec, passage["vector"])
        if score <= 0:
            continue
        scored.append((score, passage))
    scored.sort(key=lambda item: item[0], reverse=True)
    results = []
    for score, passage in scored[:top_k]:
        snippet = " ".join(passage["text"].split())[:280]
        results.append({
            "score": round(score, 4),
            "relative_path": passage["relative_path"],
            "document_type": passage["document_type"],
            "char_start": passage["char_start"],
            "snippet": snippet,
        })
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a full-folder DGML graph and queryable vector index, or query it.")
    parser.add_argument("--folder", type=Path, required=True, help="Investment folder SR root (contains 00_Index and 99_Archive).")
    parser.add_argument("--query", type=str, default=None, help="If given, query the existing index instead of building.")
    parser.add_argument("--top-k", type=int, default=8)
    args = parser.parse_args()

    if args.query:
        results = query(args.folder, args.query, args.top_k)
        print(json.dumps({"query": args.query, "results": results}, indent=2))
        return 0

    manifest = build(args.folder)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
