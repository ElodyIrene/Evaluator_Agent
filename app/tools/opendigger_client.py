from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx

from app.schemas import MetricBundle
from app.tools.redis_store import load_json, save_json


OPENDIGGER_BASE_URL = "https://oss.open-digger.cn/github"

OPENDIGGER_CACHE_TTL_SECONDS = 60 * 60 * 6
OPENDIGGER_REQUEST_TIMEOUT_SECONDS = 8
OPENDIGGER_MAX_WORKERS = 8


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


def _opendigger_metric_cache_key(owner: str, repo: str, metric_name: str) -> str:
    return f"cache:opendigger:{owner}:{repo}:{metric_name}"


def _load_opendigger_metric_from_cache(
    owner: str,
    repo: str,
    metric_name: str,
) -> Any | None:
    try:
        return load_json(_opendigger_metric_cache_key(owner, repo, metric_name))
    except Exception:
        return None


def _save_opendigger_metric_to_cache(
    owner: str,
    repo: str,
    metric_name: str,
    value: Any,
) -> None:
    try:
        save_json(
            key=_opendigger_metric_cache_key(owner, repo, metric_name),
            value=value,
            expire_seconds=OPENDIGGER_CACHE_TTL_SECONDS,
        )
    except Exception:
        return


def get_opendigger_metric(owner: str, repo: str, metric_name: str) -> Any | None:
    """Fetch one OpenDigger metric, with Redis cache."""
    cached_value = _load_opendigger_metric_from_cache(owner, repo, metric_name)

    if cached_value is not None:
        return cached_value

    url = f"{OPENDIGGER_BASE_URL}/{owner}/{repo}/{metric_name}.json"

    try:
        response = httpx.get(url, timeout=OPENDIGGER_REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        value = response.json()
        _save_opendigger_metric_to_cache(owner, repo, metric_name, value)
        return value
    except httpx.HTTPError:
        return None


def get_opendigger_metric_bundle(
    owner: str,
    repo: str,
    metric_names: list[str] | None = None,
) -> MetricBundle:
    """Fetch a group of OpenDigger metrics concurrently."""
    metric_names = metric_names or DEFAULT_METRICS

    opendigger_data: dict[str, Any] = {}
    missing_metrics: list[str] = []

    with ThreadPoolExecutor(max_workers=OPENDIGGER_MAX_WORKERS) as executor:
        future_to_metric = {
            executor.submit(get_opendigger_metric, owner, repo, metric_name): metric_name
            for metric_name in metric_names
        }

        for future in as_completed(future_to_metric):
            metric_name = future_to_metric[future]

            try:
                value = future.result()
            except Exception:
                value = None

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
    cached_openrank = _load_opendigger_metric_from_cache(owner, repo, "openrank")

    print("repo:", f"{owner}/{repo}")
    print("available metrics:", list(bundle.opendigger.keys()))
    print("missing metrics:", bundle.missing_metrics)
    print("opendigger metric count:", len(bundle.opendigger))
    print("opendigger cache exists:", cached_openrank is not None)
