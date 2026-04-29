from pathlib import Path

from app.agents.metric_collector import metric_collector_agent
from app.agents.metric_selector import metric_selector_agent
from app.agents.project_parser import project_parser_agent
from app.agents.type_classifier import type_classifier_agent
from app.schemas import EvaluationState, RetrievedDoc


KNOWLEDGE_BASE_PATH = Path("knowledge_base/metrics.md")


METRIC_TITLE_MAP = {
    "openrank": "OpenRank",
    "activity": "Activity",
    "contributors": "Contributors",
    "bus_factor": "Bus Factor",
    "issue_response_time": "Issue Response Time",
    "issue_resolution_duration": "Issue Resolution Duration",
    "change_request_response_time": "Change Request Response Time",
    "stars": "Stars",
    "forks": "Forks",
    "license": "License",
}


def _load_metric_sections() -> dict[str, str]:
    """Load metric sections from the local knowledge base."""
    text = KNOWLEDGE_BASE_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()

    sections: dict[str, list[str]] = {}
    current_title: str | None = None

    for line in lines:
        if line.startswith("## "):
            current_title = line.replace("## ", "").strip()
            sections[current_title.lower()] = [line]
        elif current_title:
            sections[current_title.lower()].append(line)

    return {
        title: "\n".join(content).strip()
        for title, content in sections.items()
    }


def rag_retrieval_agent(state: EvaluationState) -> EvaluationState:
    """Retrieve metric definitions and usage context from the knowledge base."""
    if not state.selected_metrics:
        state.errors.append("Cannot retrieve RAG context because selected_metrics is empty.")
        return state

    if not KNOWLEDGE_BASE_PATH.exists():
        state.errors.append(f"Knowledge base file not found: {KNOWLEDGE_BASE_PATH}")
        return state

    sections = _load_metric_sections()
    retrieved_docs: list[RetrievedDoc] = []
    seen_titles: set[str] = set()

    for metric in state.selected_metrics:
        title = METRIC_TITLE_MAP.get(metric.name)

        if title is None:
            continue

        section_content = sections.get(title.lower())

        if not section_content:
            continue

        if title in seen_titles:
            continue

        retrieved_docs.append(
            RetrievedDoc(
                title=title,
                content=section_content,
                source=str(KNOWLEDGE_BASE_PATH),
            )
        )
        seen_titles.add(title)

    state.retrieved_context = retrieved_docs
    return state


if __name__ == "__main__":
    state = EvaluationState(
        input_url="https://github.com/langchain-ai/langgraph"
    )

    state = project_parser_agent(state)
    state = type_classifier_agent(state)
    state = metric_collector_agent(state)
    state = metric_selector_agent(state)
    state = rag_retrieval_agent(state)

    print("owner:", state.owner)
    print("repo:", state.repo)
    print("selected metric count:", len(state.selected_metrics))
    print("retrieved context count:", len(state.retrieved_context))
    print("errors:", state.errors)

    for doc in state.retrieved_context:
        print("-", doc.title, "| source:", doc.source)
