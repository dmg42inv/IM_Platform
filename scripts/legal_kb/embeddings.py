"""Offline semantic embeddings for the legal knowledge base.

Uses a local sentence-transformer model. No document text leaves the machine.
The model is downloaded once (cached under the HuggingFace cache) and then runs
fully offline. Vectors are L2-normalised so cosine similarity is a dot product.

Vectors are a retrieval aid only - the SQLite database remains the source of
truth. This module stores/loads vectors as float32 bytes in that database.
"""

from __future__ import annotations

import os

import numpy as np

# Model is cached locally; run fully offline so no Hub HEAD calls are made
# (those trip the corporate TLS proxy). Set before importing transformers.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# Use the OS (Windows) certificate store so any first-time model download
# succeeds through a corporate TLS-inspecting proxy without disabling
# certificate verification.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # pragma: no cover - truststore optional
    pass

# A small, strong retrieval model. Override via build_kb --model if desired.
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

_MODEL_CACHE: dict[str, object] = {}


def _configure_threads() -> None:
    """Use all physical cores for CPU embedding (torch otherwise underuses them)."""
    try:
        import torch

        cores = os.cpu_count() or 4
        torch.set_num_threads(cores)
        os.environ.setdefault("OMP_NUM_THREADS", str(cores))
    except Exception:  # pragma: no cover
        pass


def load_model(model_name: str = DEFAULT_MODEL):
    """Lazily load and cache a sentence-transformer model."""
    if model_name in _MODEL_CACHE:
        return _MODEL_CACHE[model_name]
    _configure_threads()
    from sentence_transformers import SentenceTransformer  # imported lazily
    model = SentenceTransformer(model_name)
    _MODEL_CACHE[model_name] = model
    return model


def embed_texts(texts: list[str], model_name: str = DEFAULT_MODEL,
                batch_size: int = 128) -> np.ndarray:
    """Return an (n, dim) float32 array of L2-normalised embeddings."""
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    model = load_model(model_name)
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return vectors.astype(np.float32)


def embed_query(text: str, model_name: str = DEFAULT_MODEL) -> np.ndarray:
    return embed_texts([text], model_name=model_name)[0]


def to_bytes(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def from_bytes(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)
