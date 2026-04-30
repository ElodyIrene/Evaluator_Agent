from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel

from app.graph import run_evaluation_graph
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


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/evaluate")
def evaluate_project(request: EvaluateRequest) -> dict[str, Any]:
    task_id = str(uuid4())

    save_task_state(
        task_id=task_id,
        state={
            "input_url": request.url,
            "step": "started",
            "status": "running",
        },
    )

    try:
        final_state = run_evaluation_graph(request.url)
    except Exception as error:
        save_task_state(
            task_id=task_id,
            state={
                "input_url": request.url,
                "step": "evaluation",
                "status": "failed",
                "error": str(error),
            },
        )

        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(error),
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

    save_task_state(
        task_id=task_id,
        state={
            "input_url": request.url,
            "owner": final_state.owner,
            "repo": final_state.repo,
            "project_type": final_state.project_type,
            "step": "completed",
            "status": "completed",
            "overall_score": final_state.report.overall_score if final_state.report else None,
            "quality_passed": final_state.quality_result.passed if final_state.quality_result else None,
            "history_saved": history_saved,
            "errors": final_state.errors,
        },
    )

    return {
        "task_id": task_id,
        "status": "completed",
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
