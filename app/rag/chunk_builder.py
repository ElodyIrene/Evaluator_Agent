from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.rag.document_loader import KnowledgeDocument, load_markdown_documents
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
    Load all markdown documents from a directory and split them into chunks.
    """
    documents = load_markdown_documents(knowledge_base_dir)
    return build_chunks_from_documents(
        documents=documents,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


def build_knowledge_chunks_from_file(
    file_path: str | Path,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> list[KnowledgeChunk]:
    """
    Load one markdown file and split it into chunks.

    This is used by single-file indexing.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Knowledge file not found: {path.resolve()}")

    if not path.is_file():
        raise IsADirectoryError(f"Knowledge path is not a file: {path.resolve()}")

    if path.suffix.lower() != ".md":
        raise ValueError(f"Only markdown files are supported for now: {path}")

    content = path.read_text(encoding="utf-8").strip()

    if not content:
        return []

    document = KnowledgeDocument(
        source_path=path.as_posix(),
        content=content,
    )

    return build_chunks_from_documents(
        documents=[document],
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


def build_chunks_from_documents(
    documents: list[KnowledgeDocument],
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> list[KnowledgeChunk]:
    """
    Split loaded documents into RAG chunks.
    """
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
