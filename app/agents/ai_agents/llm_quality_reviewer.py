import json
import re
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI

from app.config import settings
from app.schemas import EvaluationState, QualityResult


PROMPT_PATH = Path("app/prompts/llm_quality_reviewer_prompt.md")


def _load_prompt_template() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _extract_json(text: str) -> dict[str, Any]:
    """Extract the first JSON object from LLM output."""
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)

    if not match:
        raise ValueError("LLM output does not contain a JSON object.")

    return json.loads(match.group(0))


def _build_llm() -> ChatOpenAI:
    """Build an OpenAI-compatible chat model client."""
    provider = settings.llm_provider.lower()

    if provider == "deepseek":
        api_key = getattr(settings, "deepseek_api_key", None)
        base_url = getattr(settings, "deepseek_base_url", None)

        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is not configured.")

        return ChatOpenAI(
            model=settings.model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=0,
            timeout=60,
        )

    raise ValueError(f"Unsupported LLM provider for quality reviewer: {settings.llm_provider}")


def llm_quality_reviewer_agent(state: EvaluationState) -> EvaluationState:
    """Use LLM to review semantic quality of the final report."""
    if state.report is None:
        state.errors.append("LLM quality reviewer skipped: report is missing.")
        return state

    try:
        prompt = _load_prompt_template()

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

        report = state.report.model_dump(mode="json") if state.report else None

        prompt = prompt.replace(
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

        llm = _build_llm()
        response = llm.invoke(prompt)

        parsed = _extract_json(str(response.content))
        review_result = QualityResult.model_validate(parsed)

        state.quality_result = review_result

    except Exception as error:
        state.errors.append(
            f"LLM quality reviewer failed: {error}. Keeping rule-based quality result."
        )

    return state


if __name__ == "__main__":
    from app.agents.ai_agents.llm_report_generator import llm_report_generator_agent
    from app.agents.metric_collector import metric_collector_agent
    from app.agents.metric_selector import metric_selector_agent
    from app.agents.project_parser import project_parser_agent
    from app.agents.quality_guard import quality_guard_agent
    from app.agents.rag_retrieval import rag_retrieval_agent
    from app.agents.report_generator import report_generator_agent
    from app.agents.type_classifier import type_classifier_agent

    test_state = EvaluationState(
        input_url="https://github.com/langchain-ai/langgraph"
    )

    test_state = project_parser_agent(test_state)
    test_state = type_classifier_agent(test_state)
    test_state = metric_collector_agent(test_state)
    test_state = metric_selector_agent(test_state)
    test_state = rag_retrieval_agent(test_state)
    test_state = report_generator_agent(test_state)
    test_state = llm_report_generator_agent(test_state)
    test_state = quality_guard_agent(test_state)
    test_state = llm_quality_reviewer_agent(test_state)

    print("repo:", f"{test_state.owner}/{test_state.repo}")
    print("project_type:", test_state.project_type)

    if test_state.quality_result:
        print("llm quality passed:", test_state.quality_result.passed)
        print("llm quality issues:", test_state.quality_result.issues)
        print("llm quality suggestions:", test_state.quality_result.suggestions)

    print("errors:", test_state.errors)
