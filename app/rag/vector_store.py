from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb

from app.rag.chunk_builder import KnowledgeChunk
from app.rag.embedding_service import (
    DEFAULT_EMBEDDING_DIMENSION,
    DEFAULT_EMBEDDING_MODEL,
    get_embedding_service,
)


DEFAULT_PERSIST_DIR = ".chroma/evaluator_agent"
DEFAULT_COLLECTION_NAME = "evaluator_agent_knowledge"


@dataclass(frozen=True)
class VectorSearchResult:
    """
    One result returned from the vector store.

    title:
        A readable title for the retrieved chunk.

    content:
        The retrieved text content.

    source:
        The source markdown file.

    score:
        Chroma distance score. Smaller usually means more similar.
    """

    title: str
    content: str
    source: str
    score: float


def get_chroma_client(
    persist_dir: str | Path = DEFAULT_PERSIST_DIR,
) -> chromadb.PersistentClient:
    """
    Create a persistent Chroma client.
    """
    persist_path = Path(persist_dir)
    persist_path.mkdir(parents=True, exist_ok=True)

    return chromadb.PersistentClient(path=str(persist_path))


def get_or_create_knowledge_collection(
    persist_dir: str | Path = DEFAULT_PERSIST_DIR,
    collection_name: str = DEFAULT_COLLECTION_NAME,
):
    """
    Get the knowledge collection. Create it if it does not exist.
    """
    client = get_chroma_client(persist_dir)

    return client.get_or_create_collection(
        name=collection_name,
        metadata={
            "description": "Evaluator Agent local knowledge base",
            "embedding_model": DEFAULT_EMBEDDING_MODEL,
            "embedding_dimension": DEFAULT_EMBEDDING_DIMENSION,
        },
    )


def rebuild_vector_store(
    chunks: list[KnowledgeChunk],
    persist_dir: str | Path = DEFAULT_PERSIST_DIR,
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> int:
    """
    Rebuild the local vector store from RAG chunks.

    This deletes the old collection and creates a fresh one.
    Use this when:
    - embedding model changes
    - embedding dimension changes
    - chunk strategy changes
    - metadata structure changes
    """
    client = get_chroma_client(persist_dir)

    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    collection = client.create_collection(
        name=collection_name,
        metadata={
            "description": "Evaluator Agent local knowledge base",
            "embedding_model": DEFAULT_EMBEDDING_MODEL,
            "embedding_dimension": DEFAULT_EMBEDDING_DIMENSION,
        },
    )

    return add_chunks_to_collection(collection=collection, chunks=chunks)


def add_chunks_to_vector_store(
    chunks: list[KnowledgeChunk],
    persist_dir: str | Path = DEFAULT_PERSIST_DIR,
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> int:
    """
    Add chunks to the existing vector store.

    This does not delete old chunks. For single-file update,
    call delete_chunks_by_source first.
    """
    collection = get_or_create_knowledge_collection(
        persist_dir=persist_dir,
        collection_name=collection_name,
    )

    return add_chunks_to_collection(collection=collection, chunks=chunks)


def add_chunks_to_collection(collection, chunks: list[KnowledgeChunk]) -> int:
    """
    Add chunks into a Chroma collection.
    """
    if not chunks:
        return 0

    embedding_service = get_embedding_service()
    documents = [chunk.content for chunk in chunks]
    embeddings = embedding_service.embed_documents(documents)

    collection.add(
        ids=[chunk.chunk_id for chunk in chunks],
        documents=documents,
        embeddings=embeddings,
        metadatas=[
            {
                "source": chunk.source_path,
                "chunk_index": chunk.chunk_index,
                "embedding_model": DEFAULT_EMBEDDING_MODEL,
                "embedding_dimension": DEFAULT_EMBEDDING_DIMENSION,
            }
            for chunk in chunks
        ],
    )

    return len(chunks)


def delete_chunks_by_source(
    source_path: str | Path,
    persist_dir: str | Path = DEFAULT_PERSIST_DIR,
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> int:
    """
    Delete all chunks that came from one source file.

    This is used before re-indexing a single updated file.
    """
    normalized_source = Path(source_path).as_posix()

    collection = get_or_create_knowledge_collection(
        persist_dir=persist_dir,
        collection_name=collection_name,
    )

    existing = collection.get(
        where={"source": normalized_source},
        include=["metadatas"],
    )

    ids = existing.get("ids", [])

    if not ids:
        return 0

    collection.delete(ids=ids)
    return len(ids)


def search_vector_store(
    query: str,
    top_k: int = 4,
    persist_dir: str | Path = DEFAULT_PERSIST_DIR,
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> list[VectorSearchResult]:
    """
    Search the local vector store.
    """
    client = get_chroma_client(persist_dir)
    collection = client.get_collection(name=collection_name)

    embedding_service = get_embedding_service()
    query_embedding = embedding_service.embed_query(query)

    raw_results: dict[str, Any] = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    documents = raw_results.get("documents", [[]])[0]
    metadatas = raw_results.get("metadatas", [[]])[0]
    distances = raw_results.get("distances", [[]])[0]

    results: list[VectorSearchResult] = []

    for index, document in enumerate(documents):
        metadata = metadatas[index] or {}
        source = str(metadata.get("source", "unknown"))
        chunk_index = metadata.get("chunk_index", index)
        distance = float(distances[index])

        results.append(
            VectorSearchResult(
                title=f"{Path(source).name} chunk {chunk_index}",
                content=document,
                source=source,
                score=distance,
            )
        )

    return results
