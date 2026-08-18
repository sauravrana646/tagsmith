"""Retrieve few-shot examples + top category blurbs for RAG classify."""

from __future__ import annotations

from dataclasses import dataclass

from tagsmith.classify.schema import LabeledEmail
from tagsmith.rag.embedder import Embedder, cosine_similarity
from tagsmith.rag.store import ExampleStore
from tagsmith.taxonomy.registry import SeedCategory, load_seed_categories


@dataclass(slots=True)
class RagContext:
    examples: list[LabeledEmail]
    example_scores: list[float]
    category_hints: list[str]


_SEED_EMBED_CACHE: dict[str, list[float]] = {}


class Retriever:
    def __init__(
        self,
        store: ExampleStore,
        embedder: Embedder,
        *,
        example_k: int = 5,
        category_k: int = 3,
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.example_k = example_k
        self.category_k = category_k

    def retrieve(
        self,
        query_text: str,
        *,
        exclude_gmail_ids: set[str] | None = None,
        categories: list[SeedCategory] | None = None,
    ) -> RagContext:
        hits = self.store.query_similar(
            query_text,
            k=self.example_k,
            exclude_gmail_ids=exclude_gmail_ids,
        )
        examples = [h[0] for h in hits]
        scores = [h[1] for h in hits]
        hints = self._category_hints(query_text, categories or load_seed_categories())
        return RagContext(examples=examples, example_scores=scores, category_hints=hints)

    def _category_hints(self, query_text: str, categories: list[SeedCategory]) -> list[str]:
        if self.category_k <= 0 or not categories:
            return []
        q = self.embedder.embed(query_text)
        scored: list[tuple[float, SeedCategory]] = []
        for cat in categories:
            blob = f"{cat.key}: {cat.description} " + " ".join(cat.exemplars)
            vec = _SEED_EMBED_CACHE.get(blob)
            if vec is None:
                vec = self.embedder.embed(blob)
                _SEED_EMBED_CACHE[blob] = vec
            scored.append((cosine_similarity(q, vec), cat))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [f"{cat.key}: {cat.description}" for _, cat in scored[: self.category_k]]


def format_category_hints(hints: list[str]) -> str:
    if not hints:
        return ""
    lines = ["Closest taxonomy categories (for disambiguation, not a closed set override):"]
    lines.extend(f"- {h}" for h in hints)
    return "\n".join(lines)
