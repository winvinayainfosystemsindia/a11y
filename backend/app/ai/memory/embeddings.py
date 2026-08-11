"""
Text -> vector for the ai_memory similarity index.

Deliberately self-contained: a deterministic feature-hashing embedding (the
"hashing trick" - hash each token into a fixed-size vector, L2-normalize) so
similarity search works out of the box with only the Gemini API key
configured, no separate embeddings provider/credential required. It captures
lexical overlap well enough to cluster page-type signatures and WCAG rule
descriptions written in similar vocabulary, which is what retriever.py needs.

This is the single seam for embeddings in the whole agent - every caller
goes through `embed_text`, so swapping in a real embeddings API (OpenAI,
Voyage, ...) later is a one-function change here, not a refactor.
"""
from __future__ import annotations

import hashlib
import math
import re

from app.config import settings

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def embed_text(text: str, dimensions: int | None = None) -> list[float]:
    """Deterministic, dependency-free embedding. Same text always produces
    the same vector, so it's safe to re-embed on every write without drift."""
    dims = dimensions or settings.AI_EMBEDDING_DIMENSIONS
    vector = [0.0] * dims

    tokens = _TOKEN_RE.findall((text or "").lower())
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dims
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign

    norm = math.sqrt(sum(component * component for component in vector))
    if norm == 0:
        return vector
    return [component / norm for component in vector]


def build_pattern_text(page_type_signature: str, wcag_rule_id: str, pattern_description: str) -> str:
    """Canonical text a memory row is embedded from - used identically at
    write time (memory_store.record_lesson) and query time (retriever) so
    the two vectors live in the same semantic space."""
    return f"page_type: {page_type_signature} | wcag_rule: {wcag_rule_id} | {pattern_description}"
