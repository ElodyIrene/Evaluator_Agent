from pathlib import Path

path = Path("app/agents/ai_agents/llm_quality_reviewer.py")
text = path.read_text(encoding="utf-8")

old = '''        prompt_template = _load_prompt_template()

        prompt = prompt_template.format(
            selected_metrics=_json_dumps(
                [metric.model_dump(mode="json") for metric in state.selected_metrics]
            ),
            retrieved_context=_json_dumps(
                [doc.model_dump(mode="json") for doc in state.retrieved_context]
            ),
            rule_quality_result=_json_dumps(
                state.quality_result.model_dump(mode="json")
                if state.quality_result
                else None
            ),
            report=_json_dumps(state.report.model_dump(mode="json")),
        )
'''

new = '''        prompt = _load_prompt_template()

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
'''

if old not in text:
    raise SystemExit("旧代码片段没有找到，请先发我当前文件相关内容。")

path.write_text(text.replace(old, new), encoding="utf-8")
print("updated llm_quality_reviewer.py")
