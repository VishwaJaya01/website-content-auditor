"""Content analysis foundation.

The current analysis package provides section-aware chunking and deterministic
pre-LLM heuristic signals. Embeddings, prompts, LLM calls, JSON repair, and
aggregation are intentionally deferred.
"""

from app.analysis.chunker import chunk_page
from app.analysis.duplicate_detector import detect_cross_page_duplicates
from app.analysis.embeddings import (
    SentenceTransformerEmbeddingProvider,
    build_chunk_embedding,
    cosine_similarity,
    retrieve_similar_chunks,
)
from app.analysis.heuristics import analyze_page_heuristics

__all__ = [
    "SentenceTransformerEmbeddingProvider",
    "analyze_page_heuristics",
    "build_chunk_embedding",
    "chunk_page",
    "cosine_similarity",
    "detect_cross_page_duplicates",
    "retrieve_similar_chunks",
]
