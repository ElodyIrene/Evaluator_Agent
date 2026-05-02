from __future__ import annotations

import argparse
from pathlib import Path

from app.rag.chunk_builder import (
    build_knowledge_chunks,
    build_knowledge_chunks_from_file,
)
from app.rag.vector_store import (
    add_chunks_to_vector_store,
    delete_chunks_by_source,
    rebuild_vector_store,
)


def rebuild_index(knowledge_base_dir: str = "knowledge_base") -> int:
    """
    Delete the whole vector collection and rebuild all markdown files.
    """
    chunks = build_knowledge_chunks(knowledge_base_dir=knowledge_base_dir)
    indexed_count = rebuild_vector_store(chunks)

    print(f"[Index] rebuild completed. indexed chunks: {indexed_count}", flush=True)
    return indexed_count


def index_file(file_path: str | Path) -> int:
    """
    Re-index one markdown file.

    Steps:
    1. Delete old chunks from this source file.
    2. Build new chunks from the file.
    3. Add new chunks to vector store.
    """
    normalized_file_path = Path(file_path).as_posix()

    chunks = build_knowledge_chunks_from_file(normalized_file_path)
    deleted_count = delete_chunks_by_source(normalized_file_path)
    indexed_count = add_chunks_to_vector_store(chunks)

    print(f"[Index] file: {normalized_file_path}", flush=True)
    print(f"[Index] deleted old chunks: {deleted_count}", flush=True)
    print(f"[Index] indexed new chunks: {indexed_count}", flush=True)

    return indexed_count


def index_directory(directory_path: str | Path) -> int:
    """
    Re-index all markdown files under one directory.

    This does not delete the whole collection.
    It updates files one by one.
    """
    base_path = Path(directory_path)

    if not base_path.exists():
        raise FileNotFoundError(f"Directory not found: {base_path.resolve()}")

    if not base_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {base_path.resolve()}")

    total_indexed_count = 0
    markdown_files = sorted(base_path.rglob("*.md"))

    print(f"[Index] directory: {base_path.as_posix()}", flush=True)
    print(f"[Index] markdown file count: {len(markdown_files)}", flush=True)

    for file_path in markdown_files:
        total_indexed_count += index_file(file_path)

    print(
        f"[Index] directory indexing completed. "
        f"total indexed chunks: {total_indexed_count}",
        flush=True,
    )

    return total_indexed_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage local RAG index for Evaluator Agent."
    )

    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild the whole knowledge_base index.",
    )

    group.add_argument(
        "--file",
        type=str,
        help="Re-index one markdown file.",
    )

    group.add_argument(
        "--dir",
        type=str,
        help="Re-index all markdown files under one directory.",
    )

    parser.add_argument(
        "--knowledge-base-dir",
        type=str,
        default="knowledge_base",
        help="Knowledge base directory used by --rebuild.",
    )

    args = parser.parse_args()

    if args.rebuild:
        rebuild_index(knowledge_base_dir=args.knowledge_base_dir)
        return

    if args.file:
        index_file(args.file)
        return

    if args.dir:
        index_directory(args.dir)
        return


if __name__ == "__main__":
    main()
