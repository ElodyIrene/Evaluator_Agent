from __future__ import annotations

import os
import time
from typing import Literal

import dashscope


DEFAULT_EMBEDDING_MODEL = "text-embedding-v4"
DEFAULT_EMBEDDING_DIMENSION = 1024
DEFAULT_BATCH_SIZE = 10


class DashScopeEmbeddingService:
    """
    Real embedding service based on DashScope text-embedding-v4.

    Why this service exists:
    - Document chunks and search queries should be embedded differently.
    - DashScope SDK supports text_type="document" and text_type="query".
    - text-embedding-v4 supports configurable dimensions.
    """

    def __init__(
        self,
        model: str = DEFAULT_EMBEDDING_MODEL,
        dimension: int = DEFAULT_EMBEDDING_DIMENSION,
        batch_size: int = DEFAULT_BATCH_SIZE,
        api_key: str | None = None,
        base_http_api_url: str | None = None,
        max_retries: int = 3,
        retry_seconds: float = 1.5,
    ) -> None:
        self.model = model
        self.dimension = dimension
        self.batch_size = batch_size
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self.base_http_api_url = base_http_api_url or os.getenv(
            "DASHSCOPE_BASE_HTTP_API_URL"
        )
        self.max_retries = max_retries
        self.retry_seconds = retry_seconds

        if not self.api_key:
            raise ValueError(
                "DASHSCOPE_API_KEY is not set. "
                "Please set it in PowerShell before running RAG."
            )

        dashscope.api_key = self.api_key

        if self.base_http_api_url:
            dashscope.base_http_api_url = self.base_http_api_url

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        Embed document chunks for vector indexing.

        Uses text_type='document', which is designed for content stored
        in the knowledge base.
        """
        return self._embed_texts(
            texts=texts,
            text_type="document",
            instruct=None,
        )

    def embed_query(self, text: str) -> list[float]:
        """
        Embed one query for vector search.

        Uses text_type='query', which is designed for retrieval queries.
        """
        embeddings = self._embed_texts(
            texts=[text],
            text_type="query",
            instruct=(
                "Given an open-source project evaluation query, "
                "retrieve relevant metric interpretation knowledge."
            ),
        )

        return embeddings[0]

    def _embed_texts(
        self,
        texts: list[str],
        text_type: Literal["document", "query"],
        instruct: str | None,
    ) -> list[list[float]]:
        cleaned_texts = [text.strip() for text in texts if text and text.strip()]

        if not cleaned_texts:
            return []

        all_embeddings: list[list[float]] = []

        for start in range(0, len(cleaned_texts), self.batch_size):
            batch = cleaned_texts[start : start + self.batch_size]
            batch_embeddings = self._embed_batch(
                batch=batch,
                text_type=text_type,
                instruct=instruct,
            )
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    def _embed_batch(
        self,
        batch: list[str],
        text_type: Literal["document", "query"],
        instruct: str | None,
    ) -> list[list[float]]:
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                kwargs = {
                    "model": self.model,
                    "input": batch,
                    "dimension": self.dimension,
                    "text_type": text_type,
                }

                if instruct and text_type == "query":
                    kwargs["instruct"] = instruct

                response = dashscope.TextEmbedding.call(**kwargs)

                status_code = getattr(response, "status_code", None)

                if status_code != 200:
                    message = getattr(response, "message", "")
                    code = getattr(response, "code", "")
                    request_id = getattr(response, "request_id", "")
                    raise RuntimeError(
                        "DashScope embedding request failed. "
                        f"status_code={status_code}, "
                        f"code={code}, "
                        f"message={message}, "
                        f"request_id={request_id}"
                    )

                embeddings = response.output.get("embeddings", [])

                sorted_embeddings = sorted(
                    embeddings,
                    key=lambda item: item.get("text_index", 0),
                )

                vectors = [
                    item["embedding"]
                    for item in sorted_embeddings
                    if "embedding" in item
                ]

                if len(vectors) != len(batch):
                    raise RuntimeError(
                        "DashScope returned unexpected embedding count. "
                        f"expected={len(batch)}, actual={len(vectors)}"
                    )

                return vectors

            except Exception as error:
                last_error = error

                if attempt < self.max_retries:
                    time.sleep(self.retry_seconds * attempt)

        raise RuntimeError(
            f"DashScope embedding failed after {self.max_retries} attempts: "
            f"{last_error}"
        )


def get_embedding_service() -> DashScopeEmbeddingService:
    """
    Factory function used by vector_store.py.
    """
    return DashScopeEmbeddingService()
