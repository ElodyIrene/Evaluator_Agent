from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.ai_agents.llm_report_generator import llm_report_generator_agent
from app.agents.metric_collector import metric_collector_agent
from app.agents.metric_selector import metric_selector_agent
from app.agents.project_parser import project_parser_agent
from app.agents.quality_guard import quality_guard_agent
from app.agents.rag_retrieval import rag_retrieval_agent
from app.agents.report_generator import report_generator_agent
from app.agents.type_classifier import type_classifier_agent
from app.schemas import EvaluationState


MAX_QUALITY_RETRY = 1


def _ensure_state(state: EvaluationState | dict[str, Any]) -> EvaluationState:
    """Convert LangGraph state into EvaluationState if needed."""
    if isinstance(state, EvaluationState):
        return state

    return EvaluationState.model_validate(state)


def _to_dict(state: EvaluationState) -> dict[str, Any]:
    """Convert EvaluationState back to dict for LangGraph."""
    return state.model_dump(mode="python")


def _route_on_errors(state: EvaluationState | dict[str, Any]) -> str:
    """Supervisor decision: stop early if the workflow already has fatal errors."""
    current_state = _ensure_state(state)

    if current_state.errors:
        return "end"

    return "continue"


def _route_after_llm_report(state: EvaluationState | dict[str, Any]) -> str:
    """Supervisor decision after LLM report generation.

    LLM failure is not always fatal because the rule-based report can be used as fallback.
    Continue to Quality Guard as long as a report exists.
    """
    current_state = _ensure_state(state)

    if current_state.report is not None:
        return "continue"

    return "end"


def _route_after_quality_guard(state: EvaluationState | dict[str, Any]) -> str:
    """Supervisor decision after Quality Guard.

    If the report fails quality checks, retry LLM report generation once.
    """
    current_state = _ensure_state(state)

    if current_state.quality_result is None:
        return "end"

    if current_state.quality_result.passed:
        return "end"

    if current_state.retry_count < MAX_QUALITY_RETRY:
        return "retry"

    return "end"


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


def rag_retrieval_node(state: EvaluationState | dict[str, Any]) -> dict[str, Any]:
    current_state = _ensure_state(state)
    new_state = rag_retrieval_agent(current_state)
    return _to_dict(new_state)


def report_generator_node(state: EvaluationState | dict[str, Any]) -> dict[str, Any]:
    current_state = _ensure_state(state)
    new_state = report_generator_agent(current_state)
    return _to_dict(new_state)


def llm_report_generator_node(state: EvaluationState | dict[str, Any]) -> dict[str, Any]:
    current_state = _ensure_state(state)
    new_state = llm_report_generator_agent(current_state)
    return _to_dict(new_state)


def quality_guard_node(state: EvaluationState | dict[str, Any]) -> dict[str, Any]:
    current_state = _ensure_state(state)
    new_state = quality_guard_agent(current_state)
    return _to_dict(new_state)


def prepare_quality_retry_node(state: EvaluationState | dict[str, Any]) -> dict[str, Any]:
    """Prepare state before retrying LLM report generation."""
    current_state = _ensure_state(state)

    current_state.retry_count += 1
    current_state.quality_result = None

    return _to_dict(current_state)


def build_graph():
    """Build the LangGraph backend workflow with Supervisor routing."""
    workflow = StateGraph(EvaluationState)

    workflow.add_node("project_parser", project_parser_node)
    workflow.add_node("type_classifier", type_classifier_node)
    workflow.add_node("metric_collector", metric_collector_node)
    workflow.add_node("metric_selector", metric_selector_node)
    workflow.add_node("rag_retrieval", rag_retrieval_node)
    workflow.add_node("report_generator", report_generator_node)
    workflow.add_node("llm_report_generator", llm_report_generator_node)
    workflow.add_node("quality_guard", quality_guard_node)
    workflow.add_node("prepare_quality_retry", prepare_quality_retry_node)

    workflow.set_entry_point("project_parser")

    workflow.add_conditional_edges(
        "project_parser",
        _route_on_errors,
        {
            "continue": "type_classifier",
            "end": END,
        },
    )

    workflow.add_conditional_edges(
        "type_classifier",
        _route_on_errors,
        {
            "continue": "metric_collector",
            "end": END,
        },
    )

    workflow.add_conditional_edges(
        "metric_collector",
        _route_on_errors,
        {
            "continue": "metric_selector",
            "end": END,
        },
    )

    workflow.add_conditional_edges(
        "metric_selector",
        _route_on_errors,
        {
            "continue": "rag_retrieval",
            "end": END,
        },
    )

    workflow.add_conditional_edges(
        "rag_retrieval",
        _route_on_errors,
        {
            "continue": "report_generator",
            "end": END,
        },
    )

    workflow.add_conditional_edges(
        "report_generator",
        _route_on_errors,
        {
            "continue": "llm_report_generator",
            "end": END,
        },
    )

    workflow.add_conditional_edges(
        "llm_report_generator",
        _route_after_llm_report,
        {
            "continue": "quality_guard",
            "end": END,
        },
    )

    workflow.add_conditional_edges(
        "quality_guard",
        _route_after_quality_guard,
        {
            "retry": "prepare_quality_retry",
            "end": END,
        },
    )

    workflow.add_edge("prepare_quality_retry", "llm_report_generator")

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
    print("retrieved context count:", len(final_state.retrieved_context))
    print("retry_count:", final_state.retry_count)

    if final_state.report:
        print("overall_score:", final_state.report.overall_score)
        print("dimension_scores:", final_state.report.dimension_scores)
        print("summary:", final_state.report.summary)
        print("strengths:", final_state.report.strengths)
        print("risks:", final_state.report.risks)
        print("suggestions:", final_state.report.suggestions)

    if final_state.quality_result:
        print("quality passed:", final_state.quality_result.passed)
        print("quality issues:", final_state.quality_result.issues)
        print("quality suggestions:", final_state.quality_result.suggestions)

    print("errors:", final_state.errors)
