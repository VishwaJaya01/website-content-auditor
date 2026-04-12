"""Local chunk embedding and similarity retrieval utilities."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from math import sqrt
from typing import Any

from app.config import Settings, get_settings
from app.models.analysis import ChunkEmbedding, ContentChunk, SimilarChunkMatch


class SentenceTransformerEmbeddingProvider:
    """Lazy local embedding provider backed by sentence-transformers.

    The model is loaded only when embeddings are requested. This keeps API
    startup and unit tests light while still providing a real local embedding
    path for the pipeline.
    """

    def __init__(
        self,
        *,
        model_name: str | None = None,
        settings: Settings | None = None,
        normalize_embeddings: bool = True,
    ) -> None:
        active_settings = settings or get_settings()
        self.model_name = model_name or active_settings.embedding_model
        self.normalize_embeddings = normalize_embeddings
        self._model: Any | None = None

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed plain text values with the configured local model."""

        if not texts:
            return []

        model = self._load_model()
        encoded_vectors = model.encode(
            list(texts),
            show_progress_bar=False,
            convert_to_numpy=False,
            normalize_embeddings=self.normalize_embeddings,
        )
        vectors = [_to_float_vector(vector) for vector in encoded_vectors]
        if self.normalize_embeddings:
            return [normalize_vector(vector) for vector in vectors]
        return vectors

    def embed_chunks(self, chunks: Sequence[ContentChunk]) -> list[ChunkEmbedding]:
        """Embed content chunks and preserve chunk metadata alongside vectors."""

        vectors = self.embed_texts([chunk.chunk_text for chunk in chunks])
        return [
            build_chunk_embedding(chunk, vector)
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]

    def _load_model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers is required for local embeddings. "
                    "Install project dependencies with `pip install -e .`."
                ) from exc
            self._model = SentenceTransformer(self.model_name)
        return self._model


def build_chunk_embedding(
    chunk: ContentChunk,
    vector: Sequence[float],
    *,
    normalize: bool = True,
) -> ChunkEmbedding:
    """Create a typed embedding record for a chunk."""

    vector_values = [float(value) for value in vector]
    if normalize:
        vector_values = normalize_vector(vector_values)
    return ChunkEmbedding(
        chunk_id=chunk.chunk_id,
        page_url=chunk.page_url,
        section_id=chunk.section_id,
        vector=vector_values,
        text_length=chunk.text_length,
        token_estimate=chunk.token_estimate,
        metadata={
            "page_title": chunk.page_title,
            "section_heading": chunk.section_heading,
            "section_path": chunk.section_path,
        },
    )


def retrieve_similar_chunks(
    query_chunk: ContentChunk,
    chunks: Sequence[ContentChunk],
    embeddings: Sequence[ChunkEmbedding],
    *,
    top_k: int = 5,
    min_similarity: float = 0.0,
    cross_page_only: bool = False,
) -> list[SimilarChunkMatch]:
    """Return top-k similar chunks for a query chunk."""

    if top_k <= 0:
        return []

    chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    embedding_by_id = {embedding.chunk_id: embedding for embedding in embeddings}
    query_embedding = embedding_by_id.get(query_chunk.chunk_id)
    if query_embedding is None:
        return []

    matches: list[SimilarChunkMatch] = []
    for candidate_embedding in embeddings:
        if candidate_embedding.chunk_id == query_chunk.chunk_id:
            continue

        candidate_chunk = chunk_by_id.get(candidate_embedding.chunk_id)
        if candidate_chunk is None:
            continue
        if cross_page_only and candidate_chunk.page_url == query_chunk.page_url:
            continue

        score = cosine_similarity(query_embedding.vector, candidate_embedding.vector)
        if score < min_similarity:
            continue

        matches.append(
            SimilarChunkMatch(
                query_chunk=query_chunk,
                matched_chunk=candidate_chunk,
                similarity_score=round(score, 6),
                cross_page=candidate_chunk.page_url != query_chunk.page_url,
            )
        )

    matches.sort(key=lambda match: match.similarity_score, reverse=True)
    return matches[:top_k]


def cosine_similarity(
    left_vector: Sequence[float],
    right_vector: Sequence[float],
) -> float:
    """Compute cosine similarity for two equal-length numeric vectors."""

    if len(left_vector) != len(right_vector) or not left_vector:
        return 0.0

    left_norm = vector_norm(left_vector)
    right_norm = vector_norm(right_vector)
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0

    dot_product = sum(
        left * right for left, right in zip(left_vector, right_vector, strict=True)
    )
    return dot_product / (left_norm * right_norm)


def normalize_vector(vector: Sequence[float]) -> list[float]:
    """Return a unit-normalized copy of a vector."""

    norm = vector_norm(vector)
    if norm == 0.0:
        return [0.0 for _ in vector]
    return [float(value) / norm for value in vector]


def vector_norm(vector: Sequence[float]) -> float:
    """Return Euclidean norm for a vector."""

    return sqrt(sum(float(value) * float(value) for value in vector))


def _to_float_vector(vector: Iterable[object]) -> list[float]:
    if hasattr(vector, "tolist"):
        vector = vector.tolist()
    return [float(value) for value in vector]
