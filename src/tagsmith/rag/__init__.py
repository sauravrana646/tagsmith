"""Phase 3 RAG: embeddings, example store, retrieval."""

from tagsmith.rag.embedder import HashingEmbedder, build_embedder, cosine_similarity
from tagsmith.rag.retriever import RagContext, Retriever, format_category_hints
from tagsmith.rag.store import ExampleStore, RagExample, example_text_from_email

__all__ = [
    "ExampleStore",
    "HashingEmbedder",
    "RagContext",
    "RagExample",
    "Retriever",
    "build_embedder",
    "cosine_similarity",
    "example_text_from_email",
    "format_category_hints",
]
