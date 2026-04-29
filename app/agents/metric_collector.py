from app.agents.project_parser import project_parser_agent
from app.agents.type_classifier import type_classifier_agent
from app.schemas import EvaluationState, MetricBundle
from app.tools.opendigger_client import get_opendigger_metric_bundle


def metric_collector_agent(state: EvaluationState) -> EvaluationState:
    """Collect GitHub and OpenDigger metrics."""
    if state.owner is None or state.repo is None:
        state.errors.append("Cannot collect metrics because owner or repo is missing.")
        return state

    github_metrics = {}

    if state.basic_info is not None:
        github_metrics = {
            "stars": state.basic_info.stars,
            "forks": state.basic_info.forks,
            "open_issues": state.basic_info.open_issues,
            "language": state.basic_info.language,
            "topics": state.basic_info.topics,
            "license": state.basic_info.license,
            "readme_exists": bool(state.basic_info.readme),
        }

    opendigger_bundle = get_opendigger_metric_bundle(
        owner=state.owner,
        repo=state.repo,
    )

    state.raw_metrics = MetricBundle(
        github=github_metrics,
        opendigger=opendigger_bundle.opendigger,
        missing_metrics=opendigger_bundle.missing_metrics,
    )

    return state


if __name__ == "__main__":
    state = EvaluationState(
        input_url="https://github.com/langchain-ai/langgraph"
    )

    state = project_parser_agent(state)
    state = type_classifier_agent(state)
    state = metric_collector_agent(state)

    print("owner:", state.owner)
    print("repo:", state.repo)
    print("project_type:", state.project_type)
    print("github metrics:", state.raw_metrics.github if state.raw_metrics else None)
    print("opendigger metric count:", len(state.raw_metrics.opendigger) if state.raw_metrics else 0)
    print("missing metrics:", state.raw_metrics.missing_metrics if state.raw_metrics else None)
    print("errors:", state.errors)
