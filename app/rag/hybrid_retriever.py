from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.rag.bm25_retriever import search_bm25
from app.rag.chunk_builder import build_knowledge_chunks
from app.rag.vector_store import rebuild_vector_store, search_vector_store


@dataclass(frozen=True)
class HybridSearchResult:
    """
    One result returned from hybrid retrieval.

    Hybrid retrieval combines:
    - Vector search
    - BM25 keyword search

    score:
        RRF fusion score. Larger means more relevant.

    retrieval_sources:
        Shows whether this chunk came from vector search, BM25, or both.
    """

    title: str
    content: str
    source: str
    score: float
    retrieval_sources: list[str]


def _result_key(source: str, title: str, content: str) -> str:
    """
    Build a stable key for deduplication.

    In the current project, title contains the chunk index,
    for example: metrics.md chunk 2.
    """
    return f"{source}::{title}::{hash(content)}"


def search_hybrid(
    query: str,
    top_k: int = 4,
    candidate_k: int = 8,
    vector_weight: float = 0.5,
    bm25_weight: float = 0.5,
    auto_rebuild: bool = True,
) -> list[HybridSearchResult]:
    """
    Search knowledge chunks using hybrid retrieval.

    Args:
        query: User question or generated RAG query.
        top_k: Final number of results to return.
        candidate_k: Number of candidates from each retriever.
        vector_weight: Weight for vector search ranks.
        bm25_weight: Weight for BM25 ranks.
        auto_rebuild: Rebuild vector index if Chroma collection is missing.

    Returns:
        A list of merged and ranked HybridSearchResult objects.
    """
    if not query.strip():
        return []

    vector_results = []

    try:
        vector_results = search_vector_store(query=query, top_k=candidate_k)
    except Exception:
        if not auto_rebuild:
            raise

        chunks = build_knowledge_chunks()
        rebuild_vector_store(chunks)
        vector_results = search_vector_store(query=query, top_k=candidate_k)

    bm25_results = search_bm25(query=query, top_k=candidate_k)

    rrf_k = 60.0
    merged: dict[str, dict] = {}

    for rank, result in enumerate(vector_results, start=1):
        key = _result_key(result.source, result.title, result.content)

        if key not in merged:
            merged[key] = {
                "title": result.title,
                "content": result.content,
                "source": result.source,
                "score": 0.0,
                "retrieval_sources": [],
            }

        merged[key]["score"] += vector_weight / (rrf_k + rank)
        merged[key]["retrieval_sources"].append("vector")

    for rank, result in enumerate(bm25_results, start=1):
        key = _result_key(result.source, result.title, result.content)

        if key not in merged:
            merged[key] = {
                "title": result.title,
                "content": result.content,
                "source": result.source,
                "score": 0.0,
                "retrieval_sources": [],
            }

        merged[key]["score"] += bm25_weight / (rrf_k + rank)
        merged[key]["retrieval_sources"].append("bm25")

    ranked_items = sorted(
        merged.values(),
        key=lambda item: item["score"],
        reverse=True,
    )

    results: list[HybridSearchResult] = []

    for item in ranked_items[:top_k]:
        retrieval_sources = sorted(set(item["retrieval_sources"]))

        results.append(
            HybridSearchResult(
                title=item["title"],
                content=item["content"],
                source=item["source"],
                score=float(item["score"]),
                retrieval_sources=retrieval_sources,
            )
        )

    return results


if __name__ == "__main__":
    results = search_hybrid("bus factor maintainer risk", top_k=4)

    print("result_count:", len(results))

    for index, result in enumerate(results, start=1):
        print("---")
        print("rank:", index)
        print("title:", result.title)
        print("source:", result.source)
        print("score:", round(result.score, 6))
        print("retrieval_sources:", ",".join(result.retrieval_sources))
        print("preview:", result.content[:240].replace("\n", " "))
