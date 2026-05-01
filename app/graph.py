from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.ai_agents.llm_quality_reviewer import llm_quality_reviewer_agent
from app.agents.ai_agents.llm_repair_planner import llm_repair_planner_agent
from app.agents.ai_agents.llm_report_generator import llm_report_generator_agent
from app.agents.metric_collector import metric_collector_agent
from app.agents.metric_selector import metric_selector_agent
from app.agents.project_parser import project_parser_agent
from app.agents.quality_guard import quality_guard_agent
from app.agents.rag_retrieval import rag_retrieval_agent
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
    return _to_dict(project_parser_agent(current_state))


def type_classifier_node(state: EvaluationState | dict[str, Any]) -> dict[str, Any]:
    current_state = _ensure_state(state)
    return _to_dict(type_classifier_agent(current_state))


def metric_collector_node(state: EvaluationState | dict[str, Any]) -> dict[str, Any]:
    current_state = _ensure_state(state)
    return _to_dict(metric_collector_agent(current_state))


def metric_selector_node(state: EvaluationState | dict[str, Any]) -> dict[str, Any]:
    current_state = _ensure_state(state)
    return _to_dict(metric_selector_agent(current_state))


def rag_retrieval_node(state: EvaluationState | dict[str, Any]) -> dict[str, Any]:
    current_state = _ensure_state(state)
    return _to_dict(rag_retrieval_agent(current_state))


def report_generator_node(state: EvaluationState | dict[str, Any]) -> dict[str, Any]:
    current_state = _ensure_state(state)
    return _to_dict(report_generator_agent(current_state))


def llm_report_generator_node(state: EvaluationState | dict[str, Any]) -> dict[str, Any]:
    current_state = _ensure_state(state)
    return _to_dict(llm_report_generator_agent(current_state))


def quality_guard_node(state: EvaluationState | dict[str, Any]) -> dict[str, Any]:
    current_state = _ensure_state(state)
    return _to_dict(quality_guard_agent(current_state))


def llm_quality_reviewer_node(state: EvaluationState | dict[str, Any]) -> dict[str, Any]:
    current_state = _ensure_state(state)
    return _to_dict(llm_quality_reviewer_agent(current_state))


def llm_repair_planner_node(state: EvaluationState | dict[str, Any]) -> dict[str, Any]:
    current_state = _ensure_state(state)
    return _to_dict(llm_repair_planner_agent(current_state))


def prepare_repair_node(state: EvaluationState | dict[str, Any]) -> dict[str, Any]:
    """Record repair decision and increase retry count before routing back."""
    current_state = _ensure_state(state)

    current_state.repair_history.append(
        {
            "target": current_state.repair_target or "unknown",
            "plan": current_state.repair_plan or "",
        }
    )

    current_state.repair_retry_count += 1
    return _to_dict(current_state)


def route_after_repair_planner(state: EvaluationState | dict[str, Any]) -> str:
    """Decide whether to repair or end."""
    current_state = _ensure_state(state)

    if current_state.quality_result and current_state.quality_result.passed:
        return "end"

    if current_state.repair_retry_count >= 1:
        return "end"

    if current_state.repair_target == "end":
        return "end"

    return "repair"


def route_to_repair_target(state: EvaluationState | dict[str, Any]) -> str:
    """Route back to the node selected by the repair planner."""
    current_state = _ensure_state(state)

    allowed_targets = {
        "type_classifier",
        "metric_selector",
        "rag_retrieval",
        "llm_report_generator",
    }

    if current_state.repair_target in allowed_targets:
        return current_state.repair_target

    return "llm_report_generator"


def build_graph():
    """Build the LangGraph backend workflow with repair planning."""
    workflow = StateGraph(EvaluationState)

    workflow.add_node("project_parser", project_parser_node)
    workflow.add_node("type_classifier", type_classifier_node)
    workflow.add_node("metric_collector", metric_collector_node)
    workflow.add_node("metric_selector", metric_selector_node)
    workflow.add_node("rag_retrieval", rag_retrieval_node)
    workflow.add_node("report_generator", report_generator_node)
    workflow.add_node("llm_report_generator", llm_report_generator_node)
    workflow.add_node("quality_guard", quality_guard_node)
    workflow.add_node("llm_quality_reviewer", llm_quality_reviewer_node)
    workflow.add_node("llm_repair_planner", llm_repair_planner_node)
    workflow.add_node("prepare_repair", prepare_repair_node)

    workflow.set_entry_point("project_parser")

    workflow.add_edge("project_parser", "type_classifier")
    workflow.add_edge("type_classifier", "metric_collector")
    workflow.add_edge("metric_collector", "metric_selector")
    workflow.add_edge("metric_selector", "rag_retrieval")
    workflow.add_edge("rag_retrieval", "report_generator")
    workflow.add_edge("report_generator", "llm_report_generator")
    workflow.add_edge("llm_report_generator", "quality_guard")
    workflow.add_edge("quality_guard", "llm_quality_reviewer")
    workflow.add_edge("llm_quality_reviewer", "llm_repair_planner")

    workflow.add_conditional_edges(
        "llm_repair_planner",
        route_after_repair_planner,
        {
            "repair": "prepare_repair",
            "end": END,
        },
    )

    workflow.add_conditional_edges(
        "prepare_repair",
        route_to_repair_target,
        {
            "type_classifier": "type_classifier",
            "metric_selector": "metric_selector",
            "rag_retrieval": "rag_retrieval",
            "llm_report_generator": "llm_report_generator",
        },
    )

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
    print("repair_target:", final_state.repair_target)
    print("repair_plan:", final_state.repair_plan)
    print("repair_retry_count:", final_state.repair_retry_count)

    if final_state.report:
        print("overall_score:", final_state.report.overall_score)
        print("summary:", final_state.report.summary)

    if final_state.quality_result:
        print("quality passed:", final_state.quality_result.passed)
        print("quality issues:", final_state.quality_result.issues)
        print("quality suggestions:", final_state.quality_result.suggestions)

    print("review_feedback:", final_state.review_feedback)
    print("errors:", final_state.errors)

