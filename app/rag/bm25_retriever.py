from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

from app.rag.chunk_builder import KnowledgeChunk, build_knowledge_chunks


@dataclass(frozen=True)
class BM25SearchResult:
    """
    One result returned from BM25 keyword retrieval.

    title:
        A readable title for the retrieved chunk.

    content:
        The retrieved text content.

    source:
        The source markdown file.

    score:
        BM25 score. Larger means more relevant.
    """

    title: str
    content: str
    source: str
    score: float


def tokenize(text: str) -> list[str]:
    """
    Tokenize English words, numbers, underscores, and Chinese characters.

    This simple tokenizer avoids adding extra dependencies.
    It is enough for the first BM25 version.
    """
    normalized = text.lower()
    return re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", normalized)


class BM25Retriever:
    """
    A simple in-memory BM25 retriever.

    BM25 is keyword-based retrieval.
    It is useful for exact metric names like:
    - bus factor
    - openrank
    - contributor count
    - issue response time
    """

    def __init__(
        self,
        chunks: list[KnowledgeChunk],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.chunks = chunks
        self.k1 = k1
        self.b = b

        self.tokenized_docs = [tokenize(chunk.content) for chunk in chunks]
        self.doc_lengths = [len(tokens) for tokens in self.tokenized_docs]
        self.avg_doc_length = (
            sum(self.doc_lengths) / len(self.doc_lengths)
            if self.doc_lengths
            else 0.0
        )

        self.document_frequency: dict[str, int] = {}
        for tokens in self.tokenized_docs:
            for token in set(tokens):
                self.document_frequency[token] = (
                    self.document_frequency.get(token, 0) + 1
                )

    def search(self, query: str, top_k: int = 4) -> list[BM25SearchResult]:
        query_tokens = tokenize(query)

        if not query_tokens or not self.chunks:
            return []

        scored_results: list[tuple[float, KnowledgeChunk]] = []

        for chunk, doc_tokens, doc_length in zip(
            self.chunks,
            self.tokenized_docs,
            self.doc_lengths,
        ):
            score = self._score_document(
                query_tokens=query_tokens,
                doc_tokens=doc_tokens,
                doc_length=doc_length,
            )

            if score > 0:
                scored_results.append((score, chunk))

        scored_results.sort(key=lambda item: item[0], reverse=True)

        results: list[BM25SearchResult] = []

        for score, chunk in scored_results[:top_k]:
            results.append(
                BM25SearchResult(
                    title=f"{Path(chunk.source_path).name} chunk {chunk.chunk_index}",
                    content=chunk.content,
                    source=chunk.source_path,
                    score=score,
                )
            )

        return results

    def _score_document(
        self,
        query_tokens: list[str],
        doc_tokens: list[str],
        doc_length: int,
    ) -> float:
        score = 0.0
        token_counts: dict[str, int] = {}

        for token in doc_tokens:
            token_counts[token] = token_counts.get(token, 0) + 1

        total_docs = len(self.chunks)

        for token in query_tokens:
            term_frequency = token_counts.get(token, 0)

            if term_frequency == 0:
                continue

            document_frequency = self.document_frequency.get(token, 0)
            inverse_document_frequency = math.log(
                1 + (total_docs - document_frequency + 0.5)
                / (document_frequency + 0.5)
            )

            denominator = term_frequency + self.k1 * (
                1 - self.b + self.b * doc_length / self.avg_doc_length
            )

            score += inverse_document_frequency * (
                term_frequency * (self.k1 + 1)
            ) / denominator

        return score


def search_bm25(
    query: str,
    top_k: int = 4,
    knowledge_base_dir: str = "knowledge_base",
) -> list[BM25SearchResult]:
    """
    Convenience function for BM25 search.

    It loads chunks from knowledge_base and searches them in memory.
    """
    chunks = build_knowledge_chunks(knowledge_base_dir=knowledge_base_dir)
    retriever = BM25Retriever(chunks)
    return retriever.search(query=query, top_k=top_k)


if __name__ == "__main__":
    results = search_bm25("bus factor maintainer risk", top_k=3)

    print("result_count:", len(results))

    for index, result in enumerate(results, start=1):
        print("---")
        print("rank:", index)
        print("title:", result.title)
        print("source:", result.source)
        print("score:", round(result.score, 4))
        print("preview:", result.content[:220].replace("\n", " "))
