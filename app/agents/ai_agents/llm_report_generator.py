import json
import re
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI

from app.agents.metric_collector import metric_collector_agent
from app.agents.metric_selector import metric_selector_agent
from app.agents.project_parser import project_parser_agent
from app.agents.rag_retrieval import rag_retrieval_agent
from app.agents.report_generator import report_generator_agent
from app.agents.type_classifier import type_classifier_agent
from app.config import settings
from app.schemas import EvaluationReport, EvaluationState


PROMPT_PATH = Path("app/prompts/llm_report_prompt.md")


def _load_prompt_template() -> str:
    """Load the LLM report prompt from a markdown file."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def _extract_json(text: str) -> dict[str, Any]:
    """Extract a JSON object from the LLM response."""
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"^```\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in LLM response.")

    return json.loads(match.group(0))


def _build_prompt(state: EvaluationState) -> str:
    """Fill the prompt template with current workflow state."""
    template = _load_prompt_template()

    selected_metrics = [
        metric.model_dump(mode="json")
        for metric in state.selected_metrics
    ]

    retrieved_context = [
        doc.model_dump(mode="json")
        for doc in state.retrieved_context
    ]

    rule_report = state.report.model_dump(mode="json") if state.report else None

    basic_info = None
    if state.basic_info:
        basic_info = state.basic_info.model_dump(
            mode="json",
            exclude={"readme"},
        )

    prompt = template.replace(
        "{basic_info}",
        json.dumps(basic_info, ensure_ascii=False, indent=2),
    )
    prompt = prompt.replace(
        "{project_type}",
        str(state.project_type),
    )
    prompt = prompt.replace(
        "{selected_metrics}",
        json.dumps(selected_metrics, ensure_ascii=False, indent=2),
    )
    prompt = prompt.replace(
        "{retrieved_context}",
        json.dumps(retrieved_context, ensure_ascii=False, indent=2),
    )
    prompt = prompt.replace(
        "{rule_report}",
        json.dumps(rule_report, ensure_ascii=False, indent=2),
    )

    return prompt


def _create_llm() -> ChatOpenAI:
    """Create an OpenAI-compatible chat model client."""
    provider = settings.llm_provider.lower()

    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is missing.")

        return ChatOpenAI(
            model=settings.model_name,
            temperature=0,
            api_key=settings.openai_api_key,
            timeout=60,
            max_retries=2,
        )

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


def llm_report_generator_agent(state: EvaluationState) -> EvaluationState:
    """Generate a structured evaluation report using an LLM."""
    if not state.selected_metrics:
        state.errors.append("Cannot generate LLM report because selected_metrics is empty.")
        return state

    if not state.retrieved_context:
        state.errors.append("Warning: retrieved_context is empty. LLM report will not use RAG knowledge.")

    if state.report is None:
        state = report_generator_agent(state)

    try:
        llm = _create_llm()

        prompt = _build_prompt(state)
        response = llm.invoke(prompt)

        content = response.content
        if not isinstance(content, str):
            content = str(content)

        data = _extract_json(content)
        state.report = EvaluationReport.model_validate(data)

    except Exception as error:
        state.errors.append(f"LLM report generation failed: {error}")

    return state


if __name__ == "__main__":
    state = EvaluationState(
        input_url="https://github.com/langchain-ai/langgraph"
    )

    state = project_parser_agent(state)
    state = type_classifier_agent(state)
    state = metric_collector_agent(state)
    state = metric_selector_agent(state)
    state = rag_retrieval_agent(state)
    state = report_generator_agent(state)
    state = llm_report_generator_agent(state)

    print("repo:", state.report.repo if state.report else None)
    print("project_type:", state.report.project_type if state.report else None)
    print("retrieved context count:", len(state.retrieved_context))
    print("overall_score:", state.report.overall_score if state.report else None)
    print("dimension_scores:", state.report.dimension_scores if state.report else None)
    print("summary:", state.report.summary if state.report else None)
    print("strengths:", state.report.strengths if state.report else None)
    print("risks:", state.report.risks if state.report else None)
    print("suggestions:", state.report.suggestions if state.report else None)
    print("data_sources:", state.report.data_sources if state.report else None)
    print("errors:", state.errors)
