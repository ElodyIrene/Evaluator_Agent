from app.agents.metric_collector import metric_collector_agent
from app.agents.metric_selector import metric_selector_agent
from app.agents.project_parser import project_parser_agent
from app.agents.report_generator import report_generator_agent
from app.agents.type_classifier import type_classifier_agent
from app.schemas import EvaluationState, QualityResult


REQUIRED_DIMENSIONS = [
    "Popularity / Adoption",
    "Activity",
    "Maintainability",
    "Community Health",
    "Documentation & Governance",
]


def quality_guard_agent(state: EvaluationState) -> EvaluationState:
    """Check whether the generated report is complete and reasonable."""
    issues: list[str] = []
    suggestions: list[str] = []

    if state.report is None:
        issues.append("Report is missing.")
        suggestions.append("Run report_generator_agent before quality_guard_agent.")
        state.quality_result = QualityResult(
            passed=False,
            issues=issues,
            suggestions=suggestions,
        )
        return state

    report = state.report

    if report.overall_score < 0 or report.overall_score > 100:
        issues.append("overall_score must be between 0 and 100.")
        suggestions.append("Fix the scoring logic in report_generator_agent.")

    for dimension in REQUIRED_DIMENSIONS:
        if dimension not in report.dimension_scores:
            issues.append(f"Missing dimension score: {dimension}")

    for name, score in report.dimension_scores.items():
        if score < 0 or score > 20:
            issues.append(f"Dimension score out of range: {name} = {score}")

    if not report.summary or len(report.summary.strip()) < 30:
        issues.append("Summary is missing or too short.")
        suggestions.append("Make the summary explain the project type and evaluation basis.")

    if not report.strengths:
        issues.append("Strengths list is empty.")

    if not report.risks:
        issues.append("Risks list is empty.")

    if not report.suggestions:
        issues.append("Suggestions list is empty.")

    if not report.data_sources:
        issues.append("Data sources are missing.")
        suggestions.append("Include GitHub REST API and OpenDigger as data sources.")

    if not state.selected_metrics:
        issues.append("Selected metrics are missing.")
        suggestions.append("Run metric_selector_agent before report generation.")

    passed = len(issues) == 0

    if passed:
        suggestions.append("Report passed basic quality checks.")

    state.quality_result = QualityResult(
        passed=passed,
        issues=issues,
        suggestions=suggestions,
    )

    return state


if __name__ == "__main__":
    state = EvaluationState(
        input_url="https://github.com/langchain-ai/langgraph"
    )

    state = project_parser_agent(state)
    state = type_classifier_agent(state)
    state = metric_collector_agent(state)
    state = metric_selector_agent(state)
    state = report_generator_agent(state)
    state = quality_guard_agent(state)

    print("quality passed:", state.quality_result.passed if state.quality_result else None)
    print("issues:", state.quality_result.issues if state.quality_result else None)
    print("suggestions:", state.quality_result.suggestions if state.quality_result else None)
    print("errors:", state.errors)
