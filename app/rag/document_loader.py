from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KnowledgeDocument:
    """
    A document loaded from the local knowledge base.

    source_path:
        The file path. It helps us know where a retrieved chunk comes from.

    content:
        The markdown text content.
    """

    source_path: str
    content: str


def load_markdown_documents(
    knowledge_base_dir: str | Path = "knowledge_base",
) -> list[KnowledgeDocument]:
    """
    Load all non-empty markdown files from the knowledge base directory.

    Args:
        knowledge_base_dir: The local folder that stores markdown knowledge files.

    Returns:
        A list of loaded markdown documents.
    """
    base_path = Path(knowledge_base_dir)

    if not base_path.exists():
        raise FileNotFoundError(
            f"Knowledge base directory not found: {base_path.resolve()}"
        )

    if not base_path.is_dir():
        raise NotADirectoryError(
            f"Knowledge base path is not a directory: {base_path.resolve()}"
        )

    documents: list[KnowledgeDocument] = []

    for file_path in sorted(base_path.rglob("*.md")):
        content = file_path.read_text(encoding="utf-8").strip()

        if not content:
            continue

        documents.append(
            KnowledgeDocument(
                source_path=file_path.as_posix(),
                content=content,
            )
        )

    return documents
