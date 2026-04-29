from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from app.graph import run_evaluation_graph


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
    final_state = run_evaluation_graph(request.url)

    return {
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
