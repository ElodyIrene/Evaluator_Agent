from typing import Any

from app.agents.metric_collector import metric_collector_agent
from app.agents.metric_selector import metric_selector_agent
from app.agents.project_parser import project_parser_agent
from app.agents.type_classifier import type_classifier_agent
from app.schemas import EvaluationReport, EvaluationState, SelectedMetric


def _find_metric(metrics: list[SelectedMetric], name: str) -> Any:
    for metric in metrics:
        if metric.name == name:
            return metric.value
    return None


def _to_number(value: Any, default: float = 0) -> float:
    if isinstance(value, dict) and "value" in value:
        value = value["value"]

    if isinstance(value, bool):
        return 1 if value else 0

    if isinstance(value, (int, float)):
        return float(value)

    return default


def _score_adoption(metrics: list[SelectedMetric]) -> int:
    stars = _to_number(_find_metric(metrics, "stars"))
    forks = _to_number(_find_metric(metrics, "forks"))

    score = 0

    if stars >= 10000:
        score += 12
    elif stars >= 1000:
        score += 8
    elif stars >= 100:
        score += 4

    if forks >= 1000:
        score += 8
    elif forks >= 100:
        score += 5
    elif forks >= 10:
        score += 2

    return min(score, 20)


def _score_activity(metrics: list[SelectedMetric]) -> int:
    activity = _to_number(_find_metric(metrics, "activity"))

    if activity >= 100:
        return 20
    if activity >= 30:
        return 16
    if activity >= 10:
        return 12
    if activity > 0:
        return 8

    return 6


def _score_maintainability(metrics: list[SelectedMetric]) -> int:
    open_issues = _to_number(_find_metric(metrics, "open_issues"))
    license_value = _find_metric(metrics, "license")
    readme_exists = bool(_find_metric(metrics, "readme_exists"))

    score = 10

    if open_issues < 100:
        score += 4
    elif open_issues < 1000:
        score += 2

    if license_value:
        score += 3

    if readme_exists:
        score += 3

    return min(score, 20)


def _score_community(metrics: list[SelectedMetric]) -> int:
    contributors = _to_number(_find_metric(metrics, "contributors"))
    bus_factor = _to_number(_find_metric(metrics, "bus_factor"))

    score = 0

    if contributors >= 100:
        score += 12
    elif contributors >= 30:
        score += 9
    elif contributors >= 5:
        score += 5

    if bus_factor >= 10:
        score += 8
    elif bus_factor >= 3:
        score += 5
    elif bus_factor > 0:
        score += 2

    return min(score, 20)


def _score_documentation(metrics: list[SelectedMetric]) -> int:
    readme_exists = bool(_find_metric(metrics, "readme_exists"))
    license_value = _find_metric(metrics, "license")

    score = 8

    if readme_exists:
        score += 7

    if license_value:
        score += 5

    return min(score, 20)


def report_generator_agent(state: EvaluationState) -> EvaluationState:
    """Generate a simple structured evaluation report."""
    if not state.selected_metrics:
        state.errors.append("Cannot generate report because selected_metrics is empty.")
        return state

    dimension_scores = {
        "Popularity / Adoption": _score_adoption(state.selected_metrics),
        "Activity": _score_activity(state.selected_metrics),
        "Maintainability": _score_maintainability(state.selected_metrics),
        "Community Health": _score_community(state.selected_metrics),
        "Documentation & Governance": _score_documentation(state.selected_metrics),
    }

    overall_score = sum(dimension_scores.values())

    repo_name = f"{state.owner}/{state.repo}"

    strengths = [
        "The project has clear public repository metadata and measurable open-source signals.",
        "The project exposes enough GitHub and OpenDigger data for basic health evaluation.",
    ]

    risks = [
        "This initial report is rule-based and does not yet include LLM-based reasoning.",
        "Some metric interpretations may need deeper context from README, issues, and PR history.",
    ]

    suggestions = [
        "Add LLM-based report generation after the rule-based backend workflow is stable.",
        "Add Quality Guard to check whether the final report is complete and evidence-based.",
    ]

    state.report = EvaluationReport(
        repo=repo_name,
        project_type=state.project_type or "Unknown",
        overall_score=overall_score,
        dimension_scores=dimension_scores,
        summary=f"{repo_name} is classified as {state.project_type}. The current backend generated a rule-based evaluation using GitHub and OpenDigger metrics.",
        strengths=strengths,
        risks=risks,
        suggestions=suggestions,
        data_sources=["GitHub REST API", "OpenDigger"],
    )

    return state


if __name__ == "__main__":
    state = EvaluationState(
        input_url="https://github.com/langchain-ai/langgraph"
    )

    state = project_parser_agent(state)
    state = type_classifier_agent(state)
    state = metric_collector_agent(state)
    state = metric_selector_agent(state)
    state = report_generator_agent(state)

    print("repo:", state.report.repo if state.report else None)
    print("project_type:", state.report.project_type if state.report else None)
    print("overall_score:", state.report.overall_score if state.report else None)
    print("dimension_scores:", state.report.dimension_scores if state.report else None)
    print("summary:", state.report.summary if state.report else None)
    print("errors:", state.errors)
