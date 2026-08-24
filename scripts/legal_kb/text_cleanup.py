"""Repair and normalise extracted document text.

Extracted PDF/Office text frequently contains mojibake (UTF-8 decoded as
Latin-1), e.g. a pound sign stored as the sequence "A-circumflex + pound" or a
bullet stored as "a-circumflex + em-dash". For citation-grade reporting the
cited snippet must read correctly, so repair is mandatory, not optional.

Strategy:
- Prefer `ftfy` (fixes a very broad class of encoding damage) when installed.
- Always apply a deterministic fallback map for the specific mojibake sequences
  seen in this corpus, so behaviour is stable even without ftfy.
- Normalise whitespace and re-join words hyphenated across line breaks.
"""

from __future__ import annotations

import re
import unicodedata

try:  # ftfy is optional; fallback map covers the common cases regardless.
    from ftfy import fix_text as _ftfy_fix_text
    _HAVE_FTFY = True
except Exception:  # pragma: no cover - environment dependent
    _HAVE_FTFY = False


# Deterministic repairs for the exact mojibake sequences observed in the corpus.
# Each key is the corrupted sequence; the value is the intended character.
_MOJIBAKE_MAP = {
    "â€™": "\u2019",  # right single quote
    "â€˜": "\u2018",  # left single quote
    "â€œ": "\u201c",  # left double quote
    "â€\x9d": "\u201d",  # right double quote
    "â€ ": "\u2013 ",  # en dash followed by space
    "â€”": "\u2014",  # em dash
    "â€“": "\u2013",  # en dash
    "â€¦": "\u2026",  # ellipsis
    "â—": "\u2022",  # bullet
    "â–": "\u2022",  # bullet variant
    "Â£": "\u00a3",  # pound sign
    "Â€": "\u20ac",  # euro sign preceded by stray A-circumflex
    "â‚¬": "\u20ac",  # euro sign
    "Â©": "\u00a9",
    "Â®": "\u00ae",
    "Â°": "\u00b0",
    "Â ": " ",  # non-breaking space rendered as A-circumflex + space
    "Ã©": "\u00e9",
    "Ã¨": "\u00e8",
    "Ã¼": "\u00fc",
    "Ã¶": "\u00f6",
    "Ã¤": "\u00e4",
    "Ã±": "\u00f1",
}

_DEHYPHENATE = re.compile(r"(\w)-\n(\w)")
_MULTISPACE = re.compile(r"[ \t\u00a0]{2,}")
_MULTINEWLINE = re.compile(r"\n{3,}")
_TRAILING_WS = re.compile(r"[ \t\u00a0]+(\n)")


def _apply_fallback_map(text: str) -> str:
    for bad, good in _MOJIBAKE_MAP.items():
        if bad in text:
            text = text.replace(bad, good)
    return text


def repair_encoding(text: str) -> str:
    """Fix mojibake / encoding corruption in extracted text."""
    if not text:
        return text
    if _HAVE_FTFY:
        text = _ftfy_fix_text(text)
    # Run the fallback map even after ftfy: it is cheap and covers any residue.
    text = _apply_fallback_map(text)
    return text


def normalise_whitespace(text: str) -> str:
    """Collapse redundant whitespace without destroying paragraph structure."""
    if not text:
        return text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _DEHYPHENATE.sub(r"\1\2", text)
    text = _MULTISPACE.sub(" ", text)
    text = _TRAILING_WS.sub(r"\1", text)
    text = _MULTINEWLINE.sub("\n\n", text)
    return text.strip()


def clean(text: str) -> str:
    """Full cleanup: repair encoding, normalise unicode, tidy whitespace."""
    if not text:
        return text
    text = repair_encoding(text)
    text = unicodedata.normalize("NFC", text)
    text = normalise_whitespace(text)
    return text


def mojibake_score(text: str) -> int:
    """Count residual mojibake markers - used to flag docs needing manual review."""
    if not text:
        return 0
    return sum(text.count(bad) for bad in _MOJIBAKE_MAP)
