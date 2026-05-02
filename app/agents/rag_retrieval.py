from __future__ import annotations

from app.rag.rag_service import retrieve_knowledge
from app.schemas import EvaluationState, RetrievedDoc, SelectedMetric


def _build_rag_query(state: EvaluationState) -> str:
    """
    Build a retrieval query from the current evaluation state.

    RAG should search knowledge using:
    - selected metric names
    - metric selection reasons
    - project type
    - repository name
    """
    query_parts: list[str] = []

    if state.owner and state.repo:
        query_parts.append(f"Repository: {state.owner}/{state.repo}")

    if state.project_type:
        query_parts.append(f"Project type: {state.project_type}")

    if state.selected_metrics:
        metric_lines = []

        for metric in state.selected_metrics:
            metric_lines.append(
                f"- {metric.name}: value={metric.value}, reason={metric.reason}"
            )

        query_parts.append("Selected metrics:\n" + "\n".join(metric_lines))

    return "\n\n".join(query_parts).strip()


def rag_retrieval_agent(state: EvaluationState) -> EvaluationState:
    """
    Retrieve metric knowledge from the local RAG system.

    Current retrieval pipeline:
    1. Vector search with local Chroma
    2. BM25 keyword search
    3. Hybrid fusion
    4. Local rerank

    Input:
        state.selected_metrics

    Output:
        state.retrieved_context
    """
    print("[RAG] Start retrieval.", flush=True)
    print("[RAG] retrieval mode: hybrid_search + local_rerank", flush=True)
    print("[RAG] vector retriever: Chroma", flush=True)
    print("[RAG] keyword retriever: BM25", flush=True)

    if not state.selected_metrics:
        message = "Cannot retrieve RAG context because selected_metrics is empty."
        print(f"[RAG] Skip: {message}", flush=True)
        state.errors.append(message)
        return state

    query = _build_rag_query(state)

    if not query:
        message = "Cannot retrieve RAG context because query is empty."
        print(f"[RAG] Skip: {message}", flush=True)
        state.errors.append(message)
        return state

    print(f"[RAG] query length: {len(query)}", flush=True)
    print(f"[RAG] selected metric count: {len(state.selected_metrics)}", flush=True)

    try:
        context = retrieve_knowledge(query=query, top_k=4, auto_rebuild=True)
    except Exception as error:
        message = f"RAG retrieval failed: {error}"
        print(f"[RAG] Failed: {message}", flush=True)
        state.errors.append(message)
        return state

    if not context:
        message = "RAG retrieval returned empty context."
        print(f"[RAG] Empty: {message}", flush=True)
        state.errors.append(message)
        return state

    print(f"[RAG] context length: {len(context)}", flush=True)
    print("[RAG] Retrieved context saved to state.retrieved_context.", flush=True)

    state.retrieved_context = [
        RetrievedDoc(
            title="Hybrid RAG Knowledge",
            content=context,
            source="local_chroma_bm25_rerank:knowledge_base",
        )
    ]

    return state


if __name__ == "__main__":
    state = EvaluationState(
        input_url="https://github.com/example/example",
        owner="example",
        repo="example",
        project_type="application",
        selected_metrics=[
            SelectedMetric(
                name="bus_factor",
                value=2,
                source="test",
                reason="Low bus factor may indicate maintainer dependency risk.",
            ),
            SelectedMetric(
                name="contributors",
                value=8,
                source="test",
                reason="Contributor count helps evaluate community health.",
            ),
        ],
    )

    state = rag_retrieval_agent(state)

    print("retrieved context count:", len(state.retrieved_context))
    print("errors:", state.errors)

    if state.retrieved_context:
        first_doc = state.retrieved_context[0]
        print("title:", first_doc.title)
        print("source:", first_doc.source)
        print("content preview:", first_doc.content[:600].replace("\n", " "))
