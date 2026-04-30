from pathlib import Path
import re

path = Path("app/graph.py")
text = path.read_text(encoding="utf-8")

# 1. 所有普通错误分支都应该回到 END，而不是 llm_quality_reviewer
text = text.replace('"end": "llm_quality_reviewer"', '"end": END')

# 2. 修复 _route_after_quality_guard，让通过或最终失败后进入 reviewer
route_pattern = r'def _route_after_quality_guard\(state: EvaluationState \| dict\[str, Any\]\) -> str:[\s\S]*?\n\ndef project_parser_node'

route_replacement = '''def _route_after_quality_guard(state: EvaluationState | dict[str, Any]) -> str:
    """Supervisor decision after Quality Guard.

    If the report fails quality checks, retry LLM report generation once.
    Otherwise, continue to LLM Quality Reviewer.
    """
    current_state = _ensure_state(state)

    if current_state.quality_result is None:
        return "review"

    if current_state.quality_result.passed:
        return "review"

    if current_state.retry_count < MAX_QUALITY_RETRY:
        return "retry"

    return "review"


def project_parser_node'''

text = re.sub(route_pattern, route_replacement, text)

# 3. 修复 quality_guard 的 conditional_edges 映射
quality_edge_pattern = r'workflow\.add_conditional_edges\(\n        "quality_guard",\n        _route_after_quality_guard,\n        \{\n            "retry": "prepare_quality_retry",\n            "end": END,\n        \},\n    \)'

quality_edge_replacement = '''workflow.add_conditional_edges(
        "quality_guard",
        _route_after_quality_guard,
        {
            "retry": "prepare_quality_retry",
            "review": "llm_quality_reviewer",
        },
    )'''

text = re.sub(quality_edge_pattern, quality_edge_replacement, text)

path.write_text(text, encoding="utf-8")
print("fixed graph routes")
