from typing import Any

from app.agents.metric_collector import metric_collector_agent
from app.agents.project_parser import project_parser_agent
from app.agents.type_classifier import type_classifier_agent
from app.schemas import EvaluationState, SelectedMetric


def _latest_metric_value(value: Any) -> Any:
    """Get the latest value from an OpenDigger metric object."""
    if value is None:
        return None

    if isinstance(value, dict):
        if not value:
            return None

        latest_key = sorted(value.keys())[-1]
        return {
            "date": latest_key,
            "value": value[latest_key],
        }

    if isinstance(value, list):
        if not value:
            return None

        return value[-1]

    return value


def _add_github_metric(
    selected_metrics: list[SelectedMetric],
    github_metrics: dict[str, Any],
    name: str,
    reason: str,
) -> None:
    if name not in github_metrics:
        return

    selected_metrics.append(
        SelectedMetric(
            name=name,
            value=github_metrics.get(name),
            source="github",
            reason=reason,
        )
    )


def _add_opendigger_metric(
    selected_metrics: list[SelectedMetric],
    opendigger_metrics: dict[str, Any],
    name: str,
    reason: str,
) -> None:
    if name not in opendigger_metrics:
        return

    selected_metrics.append(
        SelectedMetric(
            name=name,
            value=_latest_metric_value(opendigger_metrics.get(name)),
            source="opendigger",
            reason=reason,
        )
    )


def metric_selector_agent(state: EvaluationState) -> EvaluationState:
    """Select core metrics based on project type."""
    if state.raw_metrics is None:
        state.errors.append("Cannot select metrics because raw_metrics is missing.")
        return state

    github_metrics = state.raw_metrics.github
    opendigger_metrics = state.raw_metrics.opendigger

    selected_metrics: list[SelectedMetric] = []

    _add_github_metric(
        selected_metrics,
        github_metrics,
        "stars",
        "Stars show basic popularity and community attention.",
    )
    _add_github_metric(
        selected_metrics,
        github_metrics,
        "forks",
        "Forks show developer interest and reuse potential.",
    )
    _add_github_metric(
        selected_metrics,
        github_metrics,
        "open_issues",
        "Open issues show current maintenance pressure.",
    )
    _add_github_metric(
        selected_metrics,
        github_metrics,
        "license",
        "License affects whether users can safely adopt the project.",
    )
    _add_github_metric(
        selected_metrics,
        github_metrics,
        "readme_exists",
        "README availability is a basic documentation signal.",
    )

    project_type = state.project_type or ""

    if "AI" in project_type or "Agent" in project_type:
        _add_opendigger_metric(
            selected_metrics,
            opendigger_metrics,
            "openrank",
            "OpenRank helps measure project influence in the open-source ecosystem.",
        )
        _add_opendigger_metric(
            selected_metrics,
            opendigger_metrics,
            "activity",
            "Activity shows whether the project is still actively maintained.",
        )
        _add_opendigger_metric(
            selected_metrics,
            opendigger_metrics,
            "contributors",
            "Contributors show community participation and project sustainability.",
        )
        _add_opendigger_metric(
            selected_metrics,
            opendigger_metrics,
            "bus_factor",
            "Bus factor helps estimate whether the project depends on too few maintainers.",
        )
        _add_opendigger_metric(
            selected_metrics,
            opendigger_metrics,
            "issue_response_time",
            "Issue response time reflects how quickly maintainers respond to users.",
        )
        _add_opendigger_metric(
            selected_metrics,
            opendigger_metrics,
            "change_request_response_time",
            "PR response time reflects review efficiency and contributor experience.",
        )
    else:
        _add_opendigger_metric(
            selected_metrics,
            opendigger_metrics,
            "openrank",
            "OpenRank helps measure project influence.",
        )
        _add_opendigger_metric(
            selected_metrics,
            opendigger_metrics,
            "activity",
            "Activity shows maintenance status.",
        )
        _add_opendigger_metric(
            selected_metrics,
            opendigger_metrics,
            "contributors",
            "Contributors show community health.",
        )
        _add_opendigger_metric(
            selected_metrics,
            opendigger_metrics,
            "issues_closed",
            "Closed issues show maintenance throughput.",
        )

    state.selected_metrics = selected_metrics
    return state


if __name__ == "__main__":
    state = EvaluationState(
        input_url="https://github.com/langchain-ai/langgraph"
    )

    state = project_parser_agent(state)
    state = type_classifier_agent(state)
    state = metric_collector_agent(state)
    state = metric_selector_agent(state)

    print("owner:", state.owner)
    print("repo:", state.repo)
    print("project_type:", state.project_type)
    print("selected metric count:", len(state.selected_metrics))
    print("errors:", state.errors)

    for metric in state.selected_metrics:
        print("-", metric.name, "| source:", metric.source, "| reason:", metric.reason)
