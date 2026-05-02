from __future__ import annotations


def split_text(
    text: str,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> list[str]:
    """
    Split long text into overlapping chunks.

    Purpose:
    - RAG should not retrieve a whole large document.
    - It retrieves small chunks that are most relevant to the query.

    Args:
        text: The original document text.
        chunk_size: Maximum length of each chunk.
        chunk_overlap: Number of characters shared between neighboring chunks.

    Returns:
        A list of non-empty text chunks.
    """
    if not text:
        return []

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0.")

    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be greater than or equal to 0.")

    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size.")

    normalized_text = text.replace("\r\n", "\n").replace("\r", "\n").strip()

    if not normalized_text:
        return []

    chunks: list[str] = []
    start = 0
    text_length = len(normalized_text)

    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunk = normalized_text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= text_length:
            break

        start = end - chunk_overlap

    return chunks
