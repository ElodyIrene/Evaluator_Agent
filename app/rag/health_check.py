from __future__ import annotations

import os
from pathlib import Path

from app.rag.document_loader import load_markdown_documents
from app.rag.embedding_service import (
    DEFAULT_EMBEDDING_DIMENSION,
    DEFAULT_EMBEDDING_MODEL,
    get_embedding_service,
)
from app.rag.rag_service import retrieve_knowledge
from app.rag.vector_store import (
    DEFAULT_COLLECTION_NAME,
    get_chroma_client,
)


def check_environment() -> bool:
    """
    Check required environment variables.
    """
    print("[Health] Checking environment...", flush=True)

    api_key = os.getenv("DASHSCOPE_API_KEY")

    if not api_key:
        print("[Health] FAIL: DASHSCOPE_API_KEY is not set.", flush=True)
        return False

    print("[Health] OK: DASHSCOPE_API_KEY is set.", flush=True)
    return True


def check_embedding() -> bool:
    """
    Check whether the embedding model can be called successfully.
    """
    print("[Health] Checking embedding service...", flush=True)
    print(
        f"[Health] embedding model: {DEFAULT_EMBEDDING_MODEL}, "
        f"dimension: {DEFAULT_EMBEDDING_DIMENSION}",
        flush=True,
    )

    try:
        embedding_service = get_embedding_service()
        vector = embedding_service.embed_query("bus factor maintainer risk")
    except Exception as error:
        print(f"[Health] FAIL: embedding request failed: {error}", flush=True)
        return False

    if len(vector) != DEFAULT_EMBEDDING_DIMENSION:
        print(
            "[Health] FAIL: unexpected embedding dimension. "
            f"expected={DEFAULT_EMBEDDING_DIMENSION}, actual={len(vector)}",
            flush=True,
        )
        return False

    print(
        f"[Health] OK: embedding call succeeded. dimension={len(vector)}",
        flush=True,
    )
    return True


def check_knowledge_base() -> bool:
    """
    Check whether local markdown knowledge files exist.
    """
    print("[Health] Checking knowledge_base...", flush=True)

    knowledge_base_path = Path("knowledge_base")

    if not knowledge_base_path.exists():
        print("[Health] FAIL: knowledge_base directory does not exist.", flush=True)
        return False

    if not knowledge_base_path.is_dir():
        print("[Health] FAIL: knowledge_base is not a directory.", flush=True)
        return False

    try:
        documents = load_markdown_documents(knowledge_base_path)
    except Exception as error:
        print(f"[Health] FAIL: failed to load markdown documents: {error}", flush=True)
        return False

    if not documents:
        print("[Health] FAIL: no markdown documents found.", flush=True)
        return False

    print(f"[Health] OK: markdown document count={len(documents)}", flush=True)

    for document in documents:
        print(f"[Health] document: {document.source_path}", flush=True)

    return True


def check_chroma_collection() -> bool:
    """
    Check whether Chroma collection exists and has indexed chunks.
    """
    print("[Health] Checking Chroma collection...", flush=True)

    try:
        client = get_chroma_client()
        collection = client.get_collection(name=DEFAULT_COLLECTION_NAME)
    except Exception as error:
        print(
            "[Health] FAIL: Chroma collection is missing or unavailable. "
            f"error={error}",
            flush=True,
        )
        print(
            "[Health] Hint: run `uv run python -m app.rag.index_service --rebuild`",
            flush=True,
        )
        return False

    try:
        chunk_count = collection.count()
    except Exception as error:
        print(f"[Health] FAIL: failed to count Chroma chunks: {error}", flush=True)
        return False

    if chunk_count <= 0:
        print("[Health] FAIL: Chroma collection exists but has no chunks.", flush=True)
        print(
            "[Health] Hint: run `uv run python -m app.rag.index_service --rebuild`",
            flush=True,
        )
        return False

    print(f"[Health] OK: Chroma chunk count={chunk_count}", flush=True)
    print(f"[Health] collection metadata={collection.metadata}", flush=True)
    return True


def check_retrieval() -> bool:
    """
    Check whether end-to-end retrieval can return context.
    """
    print("[Health] Checking retrieval...", flush=True)

    try:
        context = retrieve_knowledge(
            query="bus factor maintainer risk",
            top_k=2,
            auto_rebuild=False,
        )
    except Exception as error:
        print(f"[Health] FAIL: retrieval failed: {error}", flush=True)
        return False

    if not context:
        print("[Health] FAIL: retrieval returned empty context.", flush=True)
        return False

    print(f"[Health] OK: retrieval context length={len(context)}", flush=True)
    print("[Health] context preview:", flush=True)
    print(context[:500].replace("\n", " "), flush=True)
    return True


def main() -> None:
    checks = [
        ("environment", check_environment),
        ("embedding", check_embedding),
        ("knowledge_base", check_knowledge_base),
        ("chroma_collection", check_chroma_collection),
        ("retrieval", check_retrieval),
    ]

    results: list[tuple[str, bool]] = []

    print("[Health] RAG health check started.", flush=True)

    for name, check_function in checks:
        print("", flush=True)
        result = check_function()
        results.append((name, result))

    print("", flush=True)
    print("[Health] Summary", flush=True)

    passed_count = 0

    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"[Health] {name}: {status}", flush=True)

        if result:
            passed_count += 1

    print(
        f"[Health] passed checks: {passed_count}/{len(results)}",
        flush=True,
    )

    if passed_count == len(results):
        print("[Health] Overall status: PASS", flush=True)
    else:
        print("[Health] Overall status: FAIL", flush=True)


if __name__ == "__main__":
    main()
