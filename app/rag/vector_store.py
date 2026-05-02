from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb

from app.rag.chunk_builder import KnowledgeChunk


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


class HashEmbedder:
    """
    A simple local embedder.

    This is not a professional semantic embedding model.
    It is a beginner-friendly local embedding method so we can build and verify
    the RAG pipeline without calling any external API.

    Important:
    We manually create embeddings and pass them to Chroma.
    This avoids depending on Chroma's custom embedding function interface.
    """

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = self._tokenize(text)

        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            vector[index] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))

        if norm == 0:
            return vector

        return [value / norm for value in vector]

    def _tokenize(self, text: str) -> list[str]:
        normalized = text.lower()
        return re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", normalized)


def get_chroma_client(
    persist_dir: str | Path = DEFAULT_PERSIST_DIR,
) -> chromadb.PersistentClient:
    """
    Create a persistent Chroma client.

    The database will be stored in the local project folder.
    """
    persist_path = Path(persist_dir)
    persist_path.mkdir(parents=True, exist_ok=True)

    return chromadb.PersistentClient(path=str(persist_path))


def rebuild_vector_store(
    chunks: list[KnowledgeChunk],
    persist_dir: str | Path = DEFAULT_PERSIST_DIR,
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> int:
    """
    Rebuild the local vector store from RAG chunks.

    This function deletes the old collection and creates a fresh one.
    That keeps the beginner version easy to understand.
    """
    client = get_chroma_client(persist_dir)

    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    collection = client.create_collection(
        name=collection_name,
        metadata={"description": "Evaluator Agent local knowledge base"},
    )

    if not chunks:
        return 0

    embedder = HashEmbedder()
    documents = [chunk.content for chunk in chunks]
    embeddings = embedder.embed_documents(documents)

    collection.add(
        ids=[chunk.chunk_id for chunk in chunks],
        documents=documents,
        embeddings=embeddings,
        metadatas=[
            {
                "source": chunk.source_path,
                "chunk_index": chunk.chunk_index,
            }
            for chunk in chunks
        ],
    )

    return len(chunks)


def search_vector_store(
    query: str,
    top_k: int = 4,
    persist_dir: str | Path = DEFAULT_PERSIST_DIR,
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> list[VectorSearchResult]:
    """
    Search the local vector store.

    Args:
        query: The search question or keywords.
        top_k: How many chunks to retrieve.

    Returns:
        A list of search results.
    """
    client = get_chroma_client(persist_dir)
    collection = client.get_collection(name=collection_name)

    embedder = HashEmbedder()
    query_embedding = embedder.embed_query(query)

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
