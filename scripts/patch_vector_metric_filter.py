from pathlib import Path
import re

path = Path("app/rag/vector_store.py")
text = path.read_text(encoding="utf-8")

new_similarity_search = '''def similarity_search(query: str, k: int = 5, metric_id: str | None = None) -> list[Document]:
    """Search similar chunks from Chroma.

    If metric_id is provided, search only within that metric.
    """
    vector_store = create_vector_store()

    filter_metadata = {"metric_id": metric_id} if metric_id else None

    return vector_store.similarity_search(
        query=query,
        k=k,
        filter=filter_metadata,
    )
'''

new_similarity_search_with_score = '''def similarity_search_with_score(
    query: str,
    k: int = 5,
    metric_id: str | None = None,
) -> list[tuple[Document, float]]:
    """Search similar chunks from Chroma with distance score.

    If metric_id is provided, search only within that metric.
    """
    vector_store = create_vector_store()

    filter_metadata = {"metric_id": metric_id} if metric_id else None

    return vector_store.similarity_search_with_score(
        query=query,
        k=k,
        filter=filter_metadata,
    )
'''

pattern_1 = re.compile(
    r"^def similarity_search\(.*?(?=^def similarity_search_with_score)",
    flags=re.DOTALL | re.MULTILINE,
)

pattern_2 = re.compile(
    r"^def similarity_search_with_score\(.*?(?=^def main\(\) -> None:)",
    flags=re.DOTALL | re.MULTILINE,
)

if not pattern_1.search(text):
    raise SystemExit("ERROR: similarity_search function not found")

if not pattern_2.search(text):
    raise SystemExit("ERROR: similarity_search_with_score function not found")

text = pattern_1.sub(new_similarity_search + "\n\n", text, count=1)
text = pattern_2.sub(new_similarity_search_with_score + "\n\n", text, count=1)

path.write_text(text, encoding="utf-8")

print("OK: vector search now supports metric_id filter")
