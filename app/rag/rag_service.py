from __future__ import annotations

from app.rag.chunk_builder import build_knowledge_chunks
from app.rag.vector_store import rebuild_vector_store, search_vector_store


def rebuild_knowledge_index() -> int:
    """
    Rebuild the local RAG index from markdown files in knowledge_base.

    Returns:
        Number of chunks indexed.
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

    Args:
        query: The retrieval query.
        top_k: How many chunks to retrieve.
        auto_rebuild: If the local vector store is missing, rebuild it once.

    Returns:
        A formatted string that can be inserted into the LLM prompt.
    """
    try:
        results = search_vector_store(query=query, top_k=top_k)
    except Exception:
        if not auto_rebuild:
            raise

        rebuild_knowledge_index()
        results = search_vector_store(query=query, top_k=top_k)

    if not results:
        return ""

    context_blocks: list[str] = []

    for index, result in enumerate(results, start=1):
        context_blocks.append(
            "\n".join(
                [
                    f"[Knowledge Chunk {index}]",
                    f"Source: {result.source}",
                    f"Title: {result.title}",
                    f"Score: {result.score:.4f}",
                    "Content:",
                    result.content,
                ]
            )
        )

    return "\n\n---\n\n".join(context_blocks)
