"""Tests for local embedding helpers and similarity retrieval."""

from app.analysis.embeddings import (
    SentenceTransformerEmbeddingProvider,
    build_chunk_embedding,
    cosine_similarity,
    retrieve_similar_chunks,
)
from app.models.analysis import ContentChunk


class FakeSentenceTransformerModel:
    """Tiny stand-in for sentence-transformers in unit tests."""

    def encode(
        self,
        texts: list[str],
        *,
        show_progress_bar: bool,
        convert_to_numpy: bool,
        normalize_embeddings: bool,
    ) -> list[list[float]]:
        assert show_progress_bar is False
        assert convert_to_numpy is False
        assert normalize_embeddings is True
        return [
            [1.0, 0.0] if "pricing" in text.lower() else [0.0, 1.0]
            for text in texts
        ]


def _chunk(
    chunk_id: str,
    page_url: str,
    text: str,
    section_id: str = "section-000",
) -> ContentChunk:
    return ContentChunk(
        chunk_id=chunk_id,
        page_url=page_url,
        page_title="Example",
        page_h1="Example",
        section_id=section_id,
        section_path=["Example"],
        section_heading="Example",
        section_heading_level=1,
        chunk_text=text,
        chunk_order=0,
        token_estimate=max(1, len(text) // 4),
        text_length=len(text),
    )


def test_embedding_provider_embeds_chunks_with_lazy_fake_model(monkeypatch):
    chunks = [
        _chunk("a", "https://example.com/pricing", "Pricing plans for teams"),
        _chunk("b", "https://example.com/about", "Company history and mission"),
    ]
    provider = SentenceTransformerEmbeddingProvider(model_name="fake-model")
    monkeypatch.setattr(provider, "_load_model", lambda: FakeSentenceTransformerModel())

    embeddings = provider.embed_chunks(chunks)

    assert [embedding.chunk_id for embedding in embeddings] == ["a", "b"]
    assert embeddings[0].vector == [1.0, 0.0]
    assert embeddings[1].vector == [0.0, 1.0]
    assert embeddings[0].metadata["section_heading"] == "Example"


def test_cosine_similarity_handles_similar_and_orthogonal_vectors():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_retrieve_similar_chunks_excludes_self_and_sorts_matches():
    query = _chunk("a", "https://example.com/pricing", "Pricing copy")
    close = _chunk("b", "https://example.com/services", "Similar pricing copy")
    far = _chunk("c", "https://example.com/about", "Company story")
    chunks = [query, close, far]
    embeddings = [
        build_chunk_embedding(query, [1.0, 0.0]),
        build_chunk_embedding(close, [0.98, 0.05]),
        build_chunk_embedding(far, [0.0, 1.0]),
    ]

    matches = retrieve_similar_chunks(query, chunks, embeddings, top_k=2)

    assert [match.matched_chunk.chunk_id for match in matches] == ["b", "c"]
    assert all(match.matched_chunk.chunk_id != "a" for match in matches)
    assert matches[0].similarity_score > matches[1].similarity_score


def test_retrieve_similar_chunks_can_prefer_cross_page_matches():
    query = _chunk("a", "https://example.com/pricing", "Pricing copy")
    same_page = _chunk("b", "https://example.com/pricing", "Similar pricing copy")
    cross_page = _chunk("c", "https://example.com/services", "Similar pricing copy")
    chunks = [query, same_page, cross_page]
    embeddings = [
        build_chunk_embedding(query, [1.0, 0.0]),
        build_chunk_embedding(same_page, [0.99, 0.01]),
        build_chunk_embedding(cross_page, [0.98, 0.02]),
    ]

    matches = retrieve_similar_chunks(
        query,
        chunks,
        embeddings,
        top_k=5,
        cross_page_only=True,
    )

    assert [match.matched_chunk.chunk_id for match in matches] == ["c"]
    assert matches[0].cross_page is True
