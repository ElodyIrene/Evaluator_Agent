from __future__ import annotations

from app.rag.chunk_builder import build_knowledge_chunks
from app.rag.reranker import retrieve_with_rerank
from app.rag.vector_store import rebuild_vector_store


def rebuild_knowledge_index() -> int:
    """
    Rebuild the local RAG vector index from markdown files in knowledge_base.

    BM25 is built in memory during retrieval, so only the vector index needs
    to be persisted.
    """
    chunks = build_knowledge_chunks()
    return rebuild_vector_store(chunks)


def retrieve_knowledge(
    query: str,
    top_k: int = 4,
    auto_rebuild: bool = True,
) -> str:
    """
    Retrieve relevant knowledge chunks and format them as prompt context.

    This version uses:
    1. Vector search
    2. BM25 keyword search
    3. Hybrid fusion
    4. Local rerank

    Args:
        query: The retrieval query.
        top_k: How many final chunks to return.
        auto_rebuild: Kept for compatibility. The underlying hybrid retriever
            already rebuilds the vector index if needed.

    Returns:
        A formatted string that can be inserted into the LLM prompt.
    """
    if not query.strip():
        return ""

    candidate_k = max(top_k * 2, 8)

    try:
        results = retrieve_with_rerank(
            query=query,
            top_k=top_k,
            candidate_k=candidate_k,
        )
    except Exception:
        if not auto_rebuild:
            raise

        rebuild_knowledge_index()
        results = retrieve_with_rerank(
            query=query,
            top_k=top_k,
            candidate_k=candidate_k,
        )

    if not results:
        return ""

    context_blocks: list[str] = []

    for index, result in enumerate(results, start=1):
        retrieval_sources = ", ".join(result.retrieval_sources)

        context_blocks.append(
            "\n".join(
                [
                    f"[Knowledge Chunk {index}]",
                    f"Source: {result.source}",
                    f"Title: {result.title}",
                    f"Retrieval Sources: {retrieval_sources}",
                    f"Hybrid Score: {result.original_score:.6f}",
                    f"Rerank Score: {result.rerank_score:.6f}",
                    "Content:",
                    result.content,
                ]
            )
        )

    return "\n\n---\n\n".join(context_blocks)


if __name__ == "__main__":
    count = rebuild_knowledge_index()
    print("indexed_chunk_count:", count)

    context = retrieve_knowledge(
        query="bus factor maintainer risk",
        top_k=3,
    )

    print("context_length:", len(context))
    print(context[:1200])
