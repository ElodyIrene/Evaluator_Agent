import time

from app.agents.ai_agents.llm_quality_reviewer import llm_quality_reviewer_agent
from app.agents.ai_agents.llm_report_generator import llm_report_generator_agent
from app.agents.metric_collector import metric_collector_agent
from app.agents.metric_selector import metric_selector_agent
from app.agents.project_parser import project_parser_agent
from app.agents.quality_guard import quality_guard_agent
from app.agents.rag_retrieval import rag_retrieval_agent
from app.agents.report_generator import report_generator_agent
from app.agents.type_classifier import type_classifier_agent
from app.schemas import EvaluationState


'''用于时间性能分析'''

def run_step(name, func, state):
    start = time.perf_counter()
    state = func(state)
    cost = time.perf_counter() - start
    print(f"{name}: {cost:.2f}s")
    return state


def main():
    state = EvaluationState(
        input_url="https://github.com/langchain-ai/langgraph"
    )

    total_start = time.perf_counter()

    state = run_step("project_parser", project_parser_agent, state)
    state = run_step("type_classifier", type_classifier_agent, state)
    state = run_step("metric_collector", metric_collector_agent, state)
    state = run_step("metric_selector", metric_selector_agent, state)
    state = run_step("rag_retrieval", rag_retrieval_agent, state)
    state = run_step("rule_report_generator", report_generator_agent, state)
    state = run_step("llm_report_generator", llm_report_generator_agent, state)
    state = run_step("quality_guard", quality_guard_agent, state)
    state = run_step("llm_quality_reviewer", llm_quality_reviewer_agent, state)

    if (
        state.quality_result
        and not state.quality_result.passed
        and state.review_feedback
        and state.review_retry_count < 1
    ):
        state.review_retry_count += 1
        print("rewrite triggered: yes")
        state = run_step("llm_report_rewrite", llm_report_generator_agent, state)
        state = run_step("quality_guard_after_rewrite", quality_guard_agent, state)
        state = run_step("llm_quality_reviewer_after_rewrite", llm_quality_reviewer_agent, state)
    else:
        print("rewrite triggered: no")

    total_cost = time.perf_counter() - total_start

    print("-" * 40)
    print(f"total: {total_cost:.2f}s")
    print("review_retry_count:", state.review_retry_count)
    print("quality passed:", state.quality_result.passed if state.quality_result else None)
    print("errors:", state.errors)


if __name__ == "__main__":
    main()
