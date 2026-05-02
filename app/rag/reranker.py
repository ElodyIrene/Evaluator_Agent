from __future__ import annotations

from dataclasses import dataclass

from app.rag.bm25_retriever import tokenize
from app.rag.hybrid_retriever import HybridSearchResult, search_hybrid


@dataclass(frozen=True)
class RerankedSearchResult:
    """
    One result after reranking.

    original_score:
        Score from hybrid retrieval.

    rerank_score:
        Final local rerank score. Larger means more relevant.
    """

    title: str
    content: str
    source: str
    original_score: float
    rerank_score: float
    retrieval_sources: list[str]


def rerank_results(
    query: str,
    results: list[HybridSearchResult],
    top_k: int = 4,
) -> list[RerankedSearchResult]:
    """
    Rerank hybrid retrieval results with local rules.

    This beginner-friendly reranker does not call any external model.
    It improves ordering using:
    - token overlap
    - phrase overlap
    - whether both BM25 and vector search found the chunk
    - original hybrid score
    """
    query_tokens = tokenize(query)
    unique_query_tokens = set(query_tokens)

    if not query_tokens or not results:
        return []

    scored_results: list[RerankedSearchResult] = []

    for result in results:
        content_lower = result.content.lower()
        content_tokens = tokenize(result.content)
        unique_content_tokens = set(content_tokens)

        token_overlap_score = _calculate_token_overlap_score(
            unique_query_tokens=unique_query_tokens,
            unique_content_tokens=unique_content_tokens,
        )

        phrase_score = _calculate_phrase_score(
            query_tokens=query_tokens,
            content_lower=content_lower,
        )

        source_score = _calculate_source_score(result.retrieval_sources)

        normalized_hybrid_score = result.score * 10.0

        rerank_score = (
            normalized_hybrid_score
            + token_overlap_score * 2.0
            + phrase_score * 1.5
            + source_score
        )

        scored_results.append(
            RerankedSearchResult(
                title=result.title,
                content=result.content,
                source=result.source,
                original_score=result.score,
                rerank_score=rerank_score,
                retrieval_sources=result.retrieval_sources,
            )
        )

    scored_results.sort(key=lambda item: item.rerank_score, reverse=True)

    return scored_results[:top_k]


def retrieve_with_rerank(
    query: str,
    top_k: int = 4,
    candidate_k: int = 10,
) -> list[RerankedSearchResult]:
    """
    Run hybrid retrieval first, then rerank the candidates.
    """
    candidates = search_hybrid(
        query=query,
        top_k=candidate_k,
        candidate_k=candidate_k,
    )

    return rerank_results(
        query=query,
        results=candidates,
        top_k=top_k,
    )


def _calculate_token_overlap_score(
    unique_query_tokens: set[str],
    unique_content_tokens: set[str],
) -> float:
    if not unique_query_tokens:
        return 0.0

    matched_tokens = unique_query_tokens.intersection(unique_content_tokens)

    return len(matched_tokens) / len(unique_query_tokens)


def _calculate_phrase_score(
    query_tokens: list[str],
    content_lower: str,
) -> float:
    """
    Reward exact phrase matches.

    Example:
    query: bus factor maintainer risk

    This checks:
    - bus factor
    - factor maintainer
    - maintainer risk
    """
    if len(query_tokens) < 2:
        return 0.0

    matched_phrase_count = 0
    phrase_count = 0

    for index in range(len(query_tokens) - 1):
        phrase = f"{query_tokens[index]} {query_tokens[index + 1]}"
        phrase_count += 1

        if phrase in content_lower:
            matched_phrase_count += 1

    if phrase_count == 0:
        return 0.0

    return matched_phrase_count / phrase_count


def _calculate_source_score(retrieval_sources: list[str]) -> float:
    """
    Reward chunks found by both BM25 and vector search.
    """
    source_set = set(retrieval_sources)

    if "bm25" in source_set and "vector" in source_set:
        return 0.3

    if "bm25" in source_set or "vector" in source_set:
        return 0.1

    return 0.0


if __name__ == "__main__":
    results = retrieve_with_rerank(
        query="bus factor maintainer risk",
        top_k=4,
        candidate_k=8,
    )

    print("result_count:", len(results))

    for index, result in enumerate(results, start=1):
        print("---")
        print("rank:", index)
        print("title:", result.title)
        print("source:", result.source)
        print("original_score:", round(result.original_score, 6))
        print("rerank_score:", round(result.rerank_score, 6))
        print("retrieval_sources:", ",".join(result.retrieval_sources))
        print("preview:", result.content[:260].replace("\n", " "))
