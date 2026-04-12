"""Content analysis foundation.

The current analysis package provides section-aware chunking and deterministic
pre-LLM heuristic signals, local embedding support, duplicate detection, prompt
construction, JSON repair, chunk-level LLM analysis, and page/site aggregation.
"""

from app.analysis.aggregator import aggregate_audit_result, classify_page_type
from app.analysis.analyzer import ChunkAnalyzer, analyze_chunk_with_provider
from app.analysis.chunker import chunk_page
from app.analysis.duplicate_detector import detect_cross_page_duplicates
from app.analysis.embeddings import (
    SentenceTransformerEmbeddingProvider,
    build_chunk_embedding,
    cosine_similarity,
    retrieve_similar_chunks,
)
from app.analysis.heuristics import analyze_page_heuristics
from app.analysis.json_repair import parse_json_from_text
from app.analysis.prompts import build_chunk_analysis_prompt

__all__ = [
    "ChunkAnalyzer",
    "SentenceTransformerEmbeddingProvider",
    "aggregate_audit_result",
    "analyze_chunk_with_provider",
    "analyze_page_heuristics",
    "build_chunk_embedding",
    "build_chunk_analysis_prompt",
    "chunk_page",
    "classify_page_type",
    "cosine_similarity",
    "detect_cross_page_duplicates",
    "parse_json_from_text",
    "retrieve_similar_chunks",
]
