from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from app.graph import run_evaluation_graph
from app.schemas import EvaluationState


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


def _build_response(final_state: EvaluationState) -> dict[str, Any]:
    return {
        "owner": final_state.owner,
        "repo": final_state.repo,
        "project_type": final_state.project_type,
        "report": final_state.report.model_dump(mode="json") if final_state.report else None,
        "quality_result": final_state.quality_result.model_dump(mode="json") if final_state.quality_result else None,
        "review_feedback": final_state.review_feedback,
        "repair_target": final_state.repair_target,
        "repair_plan": final_state.repair_plan,
        "repair_retry_count": final_state.repair_retry_count,
        "repair_history": final_state.repair_history,
        "selected_metrics": [
            metric.model_dump(mode="json")
            for metric in final_state.selected_metrics
        ],
        "retrieved_context_count": len(final_state.retrieved_context),
        "errors": final_state.errors,
    }


@app.post("/evaluate")
def evaluate_project(request: EvaluateRequest) -> dict[str, Any]:
    final_state = run_evaluation_graph(request.url)
    return _build_response(final_state)
