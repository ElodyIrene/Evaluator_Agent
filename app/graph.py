from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.metric_collector import metric_collector_agent
from app.agents.metric_selector import metric_selector_agent
from app.agents.project_parser import project_parser_agent
from app.agents.quality_guard import quality_guard_agent
from app.agents.report_generator import report_generator_agent
from app.agents.type_classifier import type_classifier_agent
from app.schemas import EvaluationState


def _ensure_state(state: EvaluationState | dict[str, Any]) -> EvaluationState:
    """Convert LangGraph state into EvaluationState if needed."""
    if isinstance(state, EvaluationState):
        return state

    return EvaluationState.model_validate(state)


def _to_dict(state: EvaluationState) -> dict[str, Any]:
    """Convert EvaluationState back to dict for LangGraph."""
    return state.model_dump(mode="python")


def project_parser_node(state: EvaluationState | dict[str, Any]) -> dict[str, Any]:
    current_state = _ensure_state(state)
    new_state = project_parser_agent(current_state)
    return _to_dict(new_state)


def type_classifier_node(state: EvaluationState | dict[str, Any]) -> dict[str, Any]:
    current_state = _ensure_state(state)
    new_state = type_classifier_agent(current_state)
    return _to_dict(new_state)


def metric_collector_node(state: EvaluationState | dict[str, Any]) -> dict[str, Any]:
    current_state = _ensure_state(state)
    new_state = metric_collector_agent(current_state)
    return _to_dict(new_state)


def metric_selector_node(state: EvaluationState | dict[str, Any]) -> dict[str, Any]:
    current_state = _ensure_state(state)
    new_state = metric_selector_agent(current_state)
    return _to_dict(new_state)


def report_generator_node(state: EvaluationState | dict[str, Any]) -> dict[str, Any]:
    current_state = _ensure_state(state)
    new_state = report_generator_agent(current_state)
    return _to_dict(new_state)


def quality_guard_node(state: EvaluationState | dict[str, Any]) -> dict[str, Any]:
    current_state = _ensure_state(state)
    new_state = quality_guard_agent(current_state)
    return _to_dict(new_state)


def build_graph():
    """Build the LangGraph backend workflow."""
    workflow = StateGraph(EvaluationState)

    workflow.add_node("project_parser", project_parser_node)
    workflow.add_node("type_classifier", type_classifier_node)
    workflow.add_node("metric_collector", metric_collector_node)
    workflow.add_node("metric_selector", metric_selector_node)
    workflow.add_node("report_generator", report_generator_node)
    workflow.add_node("quality_guard", quality_guard_node)

    workflow.set_entry_point("project_parser")

    workflow.add_edge("project_parser", "type_classifier")
    workflow.add_edge("type_classifier", "metric_collector")
    workflow.add_edge("metric_collector", "metric_selector")
    workflow.add_edge("metric_selector", "report_generator")
    workflow.add_edge("report_generator", "quality_guard")
    workflow.add_edge("quality_guard", END)

    return workflow.compile()


def run_evaluation_graph(input_url: str) -> EvaluationState:
    """Run the backend evaluation graph."""
    graph = build_graph()

    initial_state = EvaluationState(input_url=input_url)
    result = graph.invoke(initial_state.model_dump(mode="python"))

    return EvaluationState.model_validate(result)


if __name__ == "__main__":
    final_state = run_evaluation_graph(
        "https://github.com/langchain-ai/langgraph"
    )

    print("owner:", final_state.owner)
    print("repo:", final_state.repo)
    print("project_type:", final_state.project_type)
    print("selected metric count:", len(final_state.selected_metrics))

    if final_state.report:
        print("overall_score:", final_state.report.overall_score)
        print("dimension_scores:", final_state.report.dimension_scores)
        print("summary:", final_state.report.summary)

    if final_state.quality_result:
        print("quality passed:", final_state.quality_result.passed)
        print("quality issues:", final_state.quality_result.issues)
        print("quality suggestions:", final_state.quality_result.suggestions)

    print("errors:", final_state.errors)
