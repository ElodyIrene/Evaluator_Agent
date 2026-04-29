from typing import Any

import httpx

from app.schemas import MetricBundle


OPENDIGGER_BASE_URL = "https://oss.open-digger.cn/github"


DEFAULT_METRICS = [
    "openrank",
    "activity",
    "stars",
    "contributors",
    "new_contributors",
    "inactive_contributors",
    "bus_factor",
    "issues_new",
    "issues_closed",
    "issue_response_time",
    "issue_resolution_duration",
    "change_requests",
    "change_requests_accepted",
    "change_request_response_time",
    "change_request_resolution_duration",
]


def get_opendigger_metric(owner: str, repo: str, metric_name: str) -> Any | None:
    """Fetch one OpenDigger metric."""
    url = f"{OPENDIGGER_BASE_URL}/{owner}/{repo}/{metric_name}.json"

    try:
        response = httpx.get(url, timeout=20)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError:
        return None


def get_opendigger_metric_bundle(
    owner: str,
    repo: str,
    metric_names: list[str] | None = None,
) -> MetricBundle:
    """Fetch a group of OpenDigger metrics."""
    metric_names = metric_names or DEFAULT_METRICS

    opendigger_data: dict[str, Any] = {}
    missing_metrics: list[str] = []

    for metric_name in metric_names:
        value = get_opendigger_metric(owner, repo, metric_name)

        if value is None:
            missing_metrics.append(metric_name)
        else:
            opendigger_data[metric_name] = value

    return MetricBundle(
        github={},
        opendigger=opendigger_data,
        missing_metrics=missing_metrics,
    )


if __name__ == "__main__":
    owner = "langchain-ai"
    repo = "langgraph"

    bundle = get_opendigger_metric_bundle(owner, repo)

    print("repo:", f"{owner}/{repo}")
    print("available metrics:", list(bundle.opendigger.keys()))
    print("missing metrics:", bundle.missing_metrics)

    for name, value in bundle.opendigger.items():
        print(name, "type:", type(value).__name__)
