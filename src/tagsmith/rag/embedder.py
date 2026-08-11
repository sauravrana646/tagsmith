"""Embedding backends for Phase 3 RAG."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?", re.IGNORECASE)


class Embedder(Protocol):
    dim: int

    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder:
    """Deterministic bag-of-words hashing embedder (no network, good for tests/CI).

    Not SOTA — enough to prove the RAG plumbing and measure lift vs no-examples
    on the golden set. Swap for a hosted embedding model via settings later.
    """

    def __init__(self, *, dim: int = 256) -> None:
        if dim < 32:
            raise ValueError("dim must be >= 32")
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = _TOKEN_RE.findall(text.lower())
        if not tokens:
            return vec
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        # L2 normalize for cosine via dot product.
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            return vec
        return [v / norm for v in vec]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError("vector dims must match")
    return sum(x * y for x, y in zip(a, b, strict=True))


def build_embedder(*, dim: int = 256) -> Embedder:
    return HashingEmbedder(dim=dim)
