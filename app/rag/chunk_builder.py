from __future__ import annotations

from dataclasses import dataclass

from app.rag.document_loader import load_markdown_documents
from app.rag.document_splitter import split_text


@dataclass(frozen=True)
class KnowledgeChunk:
    """
    A small text chunk used by RAG.

    chunk_id:
        A stable id for this chunk.

    source_path:
        The markdown file this chunk comes from.

    chunk_index:
        The index of this chunk inside its source file.

    content:
        The text content of this chunk.
    """

    chunk_id: str
    source_path: str
    chunk_index: int
    content: str


def build_knowledge_chunks(
    knowledge_base_dir: str = "knowledge_base",
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> list[KnowledgeChunk]:
    """
    Load markdown documents and split them into RAG chunks.

    Args:
        knowledge_base_dir: Local folder containing markdown knowledge files.
        chunk_size: Maximum character length of each chunk.
        chunk_overlap: Number of overlapping characters between neighboring chunks.

    Returns:
        A list of KnowledgeChunk objects.
    """
    documents = load_markdown_documents(knowledge_base_dir)
    chunks: list[KnowledgeChunk] = []

    for document in documents:
        text_chunks = split_text(
            document.content,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        for chunk_index, content in enumerate(text_chunks):
            chunk_id = f"{document.source_path}::chunk-{chunk_index}"

            chunks.append(
                KnowledgeChunk(
                    chunk_id=chunk_id,
                    source_path=document.source_path,
                    chunk_index=chunk_index,
                    content=content,
                )
            )

    return chunks
