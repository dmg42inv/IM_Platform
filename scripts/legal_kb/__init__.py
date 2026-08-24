"""Citation-grade legal knowledge base pipeline.

Builds a structured, source-of-truth knowledge base on top of the already-
extracted document text (produced by build_extraction_coverage.py). Layers:

    text_cleanup       - repair encoding corruption / normalise extracted text
    structural_parser  - parse a document into sections/clauses, parties,
                         defined terms, dates, obligations, tables
    metadata_db        - SQLite source of truth (documents, versions, status,
                         clauses, parties, defined terms, obligations, citations)
    embeddings         - offline semantic embedding model + vector storage
    build_kb           - driver: extracted text -> cleaned -> parsed -> DB -> vectors
    query              - citation-grade semantic retrieval (doc + clause + status)

Design principles:
- The database is the source of truth. Vectors are a retrieval aid, never truth.
- Every retrievable unit carries a citation: document, section/clause, status.
- Existing extracted text is REUSED; we do not re-copy or re-extract files.
"""

__all__ = [
    "text_cleanup",
    "structural_parser",
    "metadata_db",
    "embeddings",
]
