from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.graph import run_evaluation_graph
from app.tools.github_client import parse_github_url
from app.tools.redis_store import list_recent_reports, load_report, save_report


app = FastAPI(
    title="Open Source Agent Evaluator",
    description="Backend-only multi-agent open-source project evaluator.",
    version="0.1.0",
)


class EvaluateRequest(BaseModel):
    url: str
    use_cached_report: bool = False


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


def _cached_payload_to_response(cached: dict[str, Any]) -> dict[str, Any]:
    """Convert saved Redis payload back to API response format."""
    payload = cached.get("report", {})

    if "evaluation_report" in payload:
        return {
            "cache_hit": True,
            "saved_at": cached.get("saved_at"),
            "owner": payload.get("owner", cached.get("owner")),
            "repo": payload.get("repo", cached.get("repo")),
            "project_type": payload.get("project_type"),
            "selected_metrics": payload.get("selected_metrics", []),
            "report": payload.get("evaluation_report"),
            "quality_result": payload.get("quality_result"),
            "errors": payload.get("errors", []),
        }

    # Backward compatibility for old Redis records.
    response = dict(payload)
    response["cache_hit"] = True
    response["saved_at"] = cached.get("saved_at")
    return response


def _build_redis_payload(response: dict[str, Any]) -> dict[str, Any]:
    """Build a clean Redis payload without report.report nesting."""
    return {
        "owner": response.get("owner"),
        "repo": response.get("repo"),
        "project_type": response.get("project_type"),
        "selected_metrics": response.get("selected_metrics", []),
        "evaluation_report": response.get("report"),
        "quality_result": response.get("quality_result"),
        "errors": response.get("errors", []),
    }


@app.post("/evaluate")
def evaluate_project(request: EvaluateRequest) -> dict[str, Any]:
    redis_warning: str | None = None

    repo_input = parse_github_url(request.url)

    if request.use_cached_report:
        try:
            cached = load_report(repo_input.owner, repo_input.repo)
        except Exception as exc:
            cached = None
            redis_warning = f"Redis cache lookup failed: {exc}"

        if cached is not None:
            return _cached_payload_to_response(cached)

    final_state = run_evaluation_graph(request.url)

    response = {
        "cache_hit": False,
        "owner": final_state.owner,
        "repo": final_state.repo,
        "project_type": final_state.project_type,
        "selected_metrics": [
            metric.model_dump(mode="json")
            for metric in final_state.selected_metrics
        ],
        "report": final_state.report.model_dump(mode="json") if final_state.report else None,
        "quality_result": final_state.quality_result.model_dump(mode="json") if final_state.quality_result else None,
        "errors": final_state.errors,
    }

    if redis_warning:
        response["redis_warning"] = redis_warning

    if final_state.owner and final_state.repo and final_state.report:
        try:
            save_report(
                owner=final_state.owner,
                repo=final_state.repo,
                report=_build_redis_payload(response),
            )
        except Exception as exc:
            response["redis_warning"] = f"Redis save failed: {exc}"

    return response


@app.get("/reports/recent")
def get_recent_reports(limit: int = 10) -> dict[str, Any]:
    try:
        reports = list_recent_reports(limit=limit)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Redis is not available: {exc}",
        ) from exc

    return {
        "count": len(reports),
        "reports": reports,
    }


@app.get("/reports/{owner}/{repo}")
def get_saved_report(owner: str, repo: str) -> dict[str, Any]:
    try:
        report = load_report(owner, repo)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Redis is not available: {exc}",
        ) from exc

    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"No saved report found for {owner}/{repo}",
        )

    return report
