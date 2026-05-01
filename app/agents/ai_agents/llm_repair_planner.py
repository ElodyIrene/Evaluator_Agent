import json
import re
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI

from app.config import settings
from app.schemas import EvaluationState


PROMPT_PATH = Path("app/prompts/llm_repair_planner_prompt.md")


ALLOWED_REPAIR_TARGETS = {
    "type_classifier",
    "metric_selector",
    "rag_retrieval",
    "llm_report_generator",
    "end",
}


def _load_prompt_template() -> str:
    """Load the LLM repair planner prompt from a markdown file."""
    return PROMPT_PATH.read_text(encoding="utf-8-sig")


def _extract_json(text: str) -> dict[str, Any]:
    """Extract a JSON object from the LLM response."""
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"^```\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    match = re.search(r"\{.*\}", text, re.DOTALL)

    if not match:
        raise ValueError("No JSON object found in LLM repair planner response.")

    return json.loads(match.group(0))


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _normalize_repair_target(target: str | None) -> str:
    """Normalize and validate repair target."""
    if not target:
        return "llm_report_generator"

    target = target.strip().lower()

    if target in ALLOWED_REPAIR_TARGETS:
        return target

    return "llm_report_generator"


def _create_llm() -> ChatOpenAI:
    """Create an OpenAI-compatible chat model client."""
    provider = settings.llm_provider.lower()

    if provider == "deepseek":
        if not settings.deepseek_api_key:
            raise ValueError("DEEPSEEK_API_KEY is missing.")

        return ChatOpenAI(
            model=settings.model_name,
            temperature=0,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            timeout=60,
            max_retries=2,
            model_kwargs={
                "response_format": {"type": "json_object"},
            },
        )

    raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")


def _build_repair_prompt(state: EvaluationState) -> str:
    """Build prompt for deciding which workflow node should be repaired."""
    template = _load_prompt_template()

    report = state.report.model_dump(mode="json") if state.report else None

    quality_result = (
        state.quality_result.model_dump(mode="json")
        if state.quality_result
        else None
    )

    selected_metrics = [
        metric.model_dump(mode="json")
        for metric in state.selected_metrics
    ]

    retrieved_context = [
        doc.model_dump(mode="json")
        for doc in state.retrieved_context
    ]

    prompt = template.replace("{owner}", str(state.owner))
    prompt = prompt.replace("{repo}", str(state.repo))
    prompt = prompt.replace("{project_type}", str(state.project_type))
    prompt = prompt.replace("{selected_metrics}", _json_dumps(selected_metrics))
    prompt = prompt.replace("{retrieved_context_count}", str(len(retrieved_context)))
    prompt = prompt.replace("{quality_result}", _json_dumps(quality_result))
    prompt = prompt.replace("{report}", _json_dumps(report))
    prompt = prompt.replace("{review_feedback}", str(state.review_feedback))

    return prompt


def _fallback_repair_target(state: EvaluationState) -> tuple[str, str]:
    """Fallback routing if LLM planner fails."""
    feedback = state.review_feedback or ""

    if "project type" in feedback.lower() or "classified" in feedback.lower():
        return (
            "type_classifier",
            "Reviewer feedback suggests the project type may be incorrect or inconsistent.",
        )

    if "metric" in feedback.lower() or "dimension score" in feedback.lower():
        return (
            "metric_selector",
            "Reviewer feedback mentions metrics or dimension scores, so selected metrics should be reconsidered.",
        )

    if (
        "context" in feedback.lower()
        or "definition" in feedback.lower()
        or "explain" in feedback.lower()
    ):
        return (
            "rag_retrieval",
            "Reviewer feedback suggests missing context or insufficient metric explanation.",
        )

    return (
        "llm_report_generator",
        "Reviewer feedback mainly concerns report quality, specificity, consistency, or actionability.",
    )


def llm_repair_planner_agent(state: EvaluationState) -> EvaluationState:
    """Plan which node should be repaired after LLM quality review fails."""
    if state.quality_result and state.quality_result.passed:
        state.repair_target = "end"
        state.repair_plan = "Quality review passed. No repair is needed."
        return state

    if state.repair_retry_count >= 1:
        state.repair_target = "end"
        state.repair_plan = "Repair retry limit reached. Stop to avoid repeated LLM loops."
        return state

    try:
        llm = _create_llm()
        prompt = _build_repair_prompt(state)

        response = llm.invoke(prompt)
        content = response.content

        if not isinstance(content, str):
            content = str(content)

        data = _extract_json(content)

        state.repair_target = _normalize_repair_target(data.get("repair_target"))
        state.repair_plan = data.get("repair_plan") or "Repair plan was not provided."

    except Exception as error:
        state.errors.append(f"LLM repair planner failed: {error}")

        target, plan = _fallback_repair_target(state)
        state.repair_target = target
        state.repair_plan = plan

    return state


if __name__ == "__main__":
    from app.schemas import QualityResult

    state = EvaluationState(input_url="x")
    state.owner = "example"
    state.repo = "repo"
    state.project_type = "AI Framework / Agent Framework"
    state.quality_result = QualityResult(
        passed=False,
        issues=["Report is too generic and suggestions are not actionable."],
        suggestions=["Rewrite the report with more evidence from selected metrics."],
    )
    state.review_feedback = "The report is too generic and suggestions are not actionable."

    prompt = _build_repair_prompt(state)
    target, plan = _fallback_repair_target(state)

    print("prompt loaded:", "Allowed repair_target values" in prompt)
    print("placeholders replaced:", "{owner}" not in prompt and "{report}" not in prompt)
    print("fallback target:", target)
    print("fallback plan:", plan)
