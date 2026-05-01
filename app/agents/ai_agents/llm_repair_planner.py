import json
import re
from typing import Any

from langchain_openai import ChatOpenAI

from app.config import settings
from app.schemas import EvaluationState


ALLOWED_REPAIR_TARGETS = {
    "type_classifier",
    "metric_selector",
    "rag_retrieval",
    "llm_report_generator",
    "end",
}


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
        )

    raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")


def _build_repair_prompt(state: EvaluationState) -> str:
    """Build prompt for deciding which workflow node should be repaired."""
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

    return f"""
You are the supervisor planner for a LangGraph multi-agent open-source project evaluator.

The LLM quality reviewer found problems in the generated report.
Your job is to decide which workflow node should be repaired next.

Allowed repair_target values:

1. "type_classifier"
Use this if the project type is probably wrong, too broad, or inconsistent with repository metadata.

2. "metric_selector"
Use this if the selected metrics are missing, irrelevant, contradictory, or insufficient for the evaluation.

3. "rag_retrieval"
Use this if the report lacks metric definitions, evaluation criteria, or background knowledge.

4. "llm_report_generator"
Use this if the selected metrics and context are enough, but the final report is generic, inconsistent, poorly written, unsupported, or not actionable.

5. "end"
Use this if the issue cannot be safely fixed automatically, or if another retry is not worth doing.

Current project:
owner: {state.owner}
repo: {state.repo}
project_type: {state.project_type}

Selected metrics:
{_json_dumps(selected_metrics)}

Retrieved context count:
{len(retrieved_context)}

Quality review result:
{_json_dumps(quality_result)}

Current report:
{_json_dumps(report)}

Previous review feedback:
{state.review_feedback}

Return valid JSON only. Do not return Markdown.

JSON schema:
{{
  "repair_target": "type_classifier | metric_selector | rag_retrieval | llm_report_generator | end",
  "repair_plan": "Concrete short plan explaining what should be fixed and why."
}}
"""


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

    if "context" in feedback.lower() or "definition" in feedback.lower() or "explain" in feedback.lower():
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
    state.quality_result = QualityResult(
        passed=False,
        issues=["Report is too generic and suggestions are not actionable."],
        suggestions=["Rewrite the report with more evidence from selected metrics."],
    )
    state.review_feedback = "The report is too generic and suggestions are not actionable."

    target, plan = _fallback_repair_target(state)

    print("fallback target:", target)
    print("fallback plan:", plan)
