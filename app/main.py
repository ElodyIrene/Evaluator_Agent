from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel

from app.graph import run_evaluation_graph
from app.tools.github_client import (
    GitHubAPIError,
    GitHubRepoNotFoundError,
    parse_github_url,
)
from app.tools.redis_store import (
    list_recent_reports,
    load_report,
    load_task_state,
    save_report,
    save_task_state,
)


app = FastAPI(
    title="Open Source Agent Evaluator",
    description="Backend-only multi-agent open-source project evaluator.",
    version="0.1.0",
)


class EvaluateRequest(BaseModel):
    url: str
    use_cached_report: bool = False


def _safe_save_task_state(task_id: str, state: dict[str, Any]) -> None:
    try:
        save_task_state(
            task_id=task_id,
            state=state,
        )
    except Exception:
        return


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/evaluate")
def evaluate_project(request: EvaluateRequest) -> dict[str, Any]:
    task_id = str(uuid4())

    try:
        repo_input = parse_github_url(request.url)
    except ValueError as error:
        _safe_save_task_state(
            task_id=task_id,
            state={
                "input_url": request.url,
                "step": "input_validation",
                "status": "failed",
                "error_type": "invalid_github_url",
                "error": str(error),
            },
        )

        return {
            "task_id": task_id,
            "status": "failed",
            "error_type": "invalid_github_url",
            "message": str(error),
        }

    if request.use_cached_report:
        try:
            cached_report = load_report(
                owner=repo_input.owner,
                repo=repo_input.repo,
            )

            if cached_report is not None:
                _safe_save_task_state(
                    task_id=task_id,
                    state={
                        "input_url": request.url,
                        "owner": repo_input.owner,
                        "repo": repo_input.repo,
                        "step": "cache_lookup",
                        "status": "completed",
                        "cache_hit": True,
                    },
                )

                return {
                    "task_id": task_id,
                    "status": "completed",
                    "cache_hit": True,
                    "owner": repo_input.owner,
                    "repo": repo_input.repo,
                    "report": cached_report,
                    "errors": [],
                }

        except Exception:
            pass

    _safe_save_task_state(
        task_id=task_id,
        state={
            "input_url": request.url,
            "step": "started",
            "status": "running",
        },
    )

    try:
        final_state = run_evaluation_graph(request.url)

    except GitHubRepoNotFoundError as error:
        _safe_save_task_state(
            task_id=task_id,
            state={
                "input_url": request.url,
                "step": "project_parser",
                "status": "failed",
                "error_type": "github_repo_not_found",
                "error": str(error),
            },
        )

        return {
            "task_id": task_id,
            "status": "failed",
            "error_type": "github_repo_not_found",
            "message": str(error),
        }

    except GitHubAPIError as error:
        _safe_save_task_state(
            task_id=task_id,
            state={
                "input_url": request.url,
                "step": "github_api",
                "status": "failed",
                "error_type": "github_api_error",
                "error": str(error),
            },
        )

        return {
            "task_id": task_id,
            "status": "failed",
            "error_type": "github_api_error",
            "message": str(error),
        }

    except Exception as error:
        _safe_save_task_state(
            task_id=task_id,
            state={
                "input_url": request.url,
                "step": "evaluation",
                "status": "failed",
                "error_type": "evaluation_failed",
                "error": str(error),
            },
        )

        return {
            "task_id": task_id,
            "status": "failed",
            "error_type": "evaluation_failed",
            "message": str(error),
        }

    history_saved = False

    if final_state.owner and final_state.repo and final_state.report:
        try:
            save_report(
                owner=final_state.owner,
                repo=final_state.repo,
                report=final_state.report.model_dump(mode="json"),
            )
            history_saved = True
        except Exception as error:
            final_state.errors.append(f"Failed to save report history: {error}")

    _safe_save_task_state(
        task_id=task_id,
        state={
            "input_url": request.url,
            "owner": final_state.owner,
            "repo": final_state.repo,
            "project_type": final_state.project_type,
            "step": "completed",
            "status": "completed",
            "cache_hit": False,
            "overall_score": final_state.report.overall_score if final_state.report else None,
            "quality_passed": final_state.quality_result.passed if final_state.quality_result else None,
            "history_saved": history_saved,
            "errors": final_state.errors,
        },
    )

    return {
        "task_id": task_id,
        "status": "completed",
        "cache_hit": False,
        "owner": final_state.owner,
        "repo": final_state.repo,
        "project_type": final_state.project_type,
        "selected_metrics": [
            metric.model_dump(mode="json")
            for metric in final_state.selected_metrics
        ],
        "retrieved_context_count": len(final_state.retrieved_context),
        "report": final_state.report.model_dump(mode="json") if final_state.report else None,
        "quality_result": final_state.quality_result.model_dump(mode="json") if final_state.quality_result else None,
        "history_saved": history_saved,
        "errors": final_state.errors,
    }


@app.get("/tasks/{task_id}")
def get_task_state(task_id: str) -> dict[str, Any]:
    task_state = load_task_state(task_id)

    if task_state is None:
        return {
            "found": False,
            "task_id": task_id,
            "task_state": None,
        }

    return {
        "found": True,
        "task_id": task_id,
        "task_state": task_state,
    }


@app.get("/reports/recent")
def get_recent_reports(limit: int = 10) -> dict[str, Any]:
    reports = list_recent_reports(limit=limit)

    return {
        "count": len(reports),
        "reports": reports,
    }


@app.get("/reports/{owner}/{repo}")
def get_report(owner: str, repo: str) -> dict[str, Any]:
    report = load_report(owner=owner, repo=repo)

    if report is None:
        return {
            "found": False,
            "owner": owner,
            "repo": repo,
            "report": None,
        }

    return {
        "found": True,
        "owner": owner,
        "repo": repo,
        "report": report,
    }
