from app.graph import run_evaluation_graph


state = run_evaluation_graph(
    "https://github.com/langchain-ai/langgraph"
)

report = state.report

print("quality passed:", state.quality_result.passed if state.quality_result else None)
print("errors:", state.errors)
print()
print("overall_score:", report.overall_score if report else None)
print("dimension_scores:", report.dimension_scores if report else None)
print()
print("summary:")
print(report.summary if report else None)
print()
print("strengths:")
for item in report.strengths if report else []:
    print("-", item)
print()
print("risks:")
for item in report.risks if report else []:
    print("-", item)
print()
print("suggestions:")
for item in report.suggestions if report else []:
    print("-", item)
print()
print("quality suggestions:")
for item in state.quality_result.suggestions if state.quality_result else []:
    print("-", item)
print()
print("repair_history:", state.repair_history)
