import json
import re
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI

from app.config import settings
from app.tools.reflection_memory import save_report_reflection_suggestions
from app.schemas import EvaluationState, QualityResult


PROMPT_PATH = Path("app/prompts/llm_quality_reviewer_prompt.md")


def _load_prompt_template() -> str:
    """Load the LLM quality reviewer prompt from a markdown file."""
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
        raise ValueError("No JSON object found in LLM reviewer response.")

    return json.loads(match.group(0))


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


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


def _build_review_prompt(state: EvaluationState) -> str:
    """Build the prompt for LLM quality review from prompt template."""
    template = _load_prompt_template()

    report = state.report.model_dump(mode="json") if state.report else None

    selected_metrics = [
        metric.model_dump(mode="json")
        for metric in state.selected_metrics
    ]

    retrieved_context = [
        doc.model_dump(mode="json")
        for doc in state.retrieved_context
    ]

    rule_quality_result = (
        state.quality_result.model_dump(mode="json")
        if state.quality_result
        else None
    )

    prompt = template.replace(
        "{selected_metrics}",
        _json_dumps(selected_metrics),
    )
    prompt = prompt.replace(
        "{retrieved_context}",
        _json_dumps(retrieved_context),
    )
    prompt = prompt.replace(
        "{rule_quality_result}",
        _json_dumps(rule_quality_result),
    )
    prompt = prompt.replace(
        "{report}",
        _json_dumps(report),
    )

    return prompt


def _clean_reviewer_result(
    state: EvaluationState,
    issues: list[str],
    suggestions: list[str],
) -> tuple[list[str], list[str]]:
    """Remove reviewer issues that are contradicted by deterministic checks."""
    if state.report is None:
        return issues, suggestions

    cleaned_issues: list[str] = []

    dimension_sum = sum(state.report.dimension_scores.values())
    score_matches = dimension_sum == state.report.overall_score

    for issue in issues:
        issue_lower = issue.lower()

        is_score_sum_issue = (
            "sum" in issue_lower
            and (
                "overall_score" in issue_lower
                or "overall score" in issue_lower
                or "dimension_scores" in issue_lower
                or "dimension scores" in issue_lower
            )
        )

        if is_score_sum_issue and score_matches:
            continue

        cleaned_issues.append(issue)

    cleaned_suggestions: list[str] = []

    for suggestion in suggestions:
        suggestion_lower = suggestion.lower()

        is_score_sum_suggestion = (
            "sum" in suggestion_lower
            and (
                "overall_score" in suggestion_lower
                or "overall score" in suggestion_lower
                or "dimension_scores" in suggestion_lower
                or "dimension scores" in suggestion_lower
            )
        )

        if is_score_sum_suggestion and score_matches:
            continue

        cleaned_suggestions.append(suggestion)

    return cleaned_issues, cleaned_suggestions


def _save_review_feedback(state: EvaluationState) -> EvaluationState:
    """Save reviewer issues and suggestions into state.review_feedback."""
    if state.quality_result is None:
        return state

    if state.quality_result.passed:
        state.review_feedback = None
        return state

    issue_text = "\n".join(
        f"- {issue}" for issue in state.quality_result.issues
    )
    suggestion_text = "\n".join(
        f"- {suggestion}" for suggestion in state.quality_result.suggestions
    )

    state.review_feedback = f"""
The previous report did not pass LLM quality review.

Issues:
{issue_text}

Suggestions:
{suggestion_text}
""".strip()

    return state


def llm_quality_reviewer_agent(state: EvaluationState) -> EvaluationState:
    """Review the generated report with an LLM and save feedback if it fails."""
    if state.report is None:
        state.quality_result = QualityResult(
            passed=False,
            issues=["Report is missing."],
            suggestions=["Run report generation before LLM quality review."],
        )
        state = _save_review_feedback(state)
        return state

    try:
        llm = _create_llm()
        prompt = _build_review_prompt(state)

        response = llm.invoke(prompt)
        content = response.content

        if not isinstance(content, str):
            content = str(content)

        data = _extract_json(content)

        issues = data.get("issues", [])
        suggestions = data.get("suggestions", [])

        issues, suggestions = _clean_reviewer_result(
            state=state,
            issues=issues,
            suggestions=suggestions,
        )

        passed = bool(data.get("passed", False))
        if not issues:
            passed = True

        state.quality_result = QualityResult(
            passed=passed,
            issues=issues,
            suggestions=suggestions,
        )

        save_report_reflection_suggestions(suggestions)

        state = _save_review_feedback(state)

    except Exception as error:
        state.errors.append(f"LLM quality review failed: {error}")

        # If rule-based Quality Guard already produced a result, keep it.
        # The LLM reviewer failing to return valid JSON should not automatically
        # make the whole report fail.
        if state.quality_result is None:
            state.quality_result = QualityResult(
                passed=False,
                issues=[
                    "LLM quality review failed and no rule-based quality result is available."
                ],
                suggestions=["Retry later or inspect the report manually."],
            )

        state = _save_review_feedback(state)

    return state


if __name__ == "__main__":
    from app.graph import run_evaluation_graph

    state = run_evaluation_graph(
        "https://github.com/langchain-ai/langgraph"
    )

    state = llm_quality_reviewer_agent(state)

    print("quality passed:", state.quality_result.passed if state.quality_result else None)
    print("issues:", state.quality_result.issues if state.quality_result else None)
    print("suggestions:", state.quality_result.suggestions if state.quality_result else None)
    print("review_feedback:", state.review_feedback)
    print("errors:", state.errors)

