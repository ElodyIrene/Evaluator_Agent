from pathlib import Path


REFLECTION_MEMORY_PATH = Path("app/memory/report_reflection_memory.md")
MAX_MEMORY_ITEMS = 20


CANONICAL_LESSONS = {
    "response_time": "When discussing response time metrics, mention the metric name, time period, and quantile when available.",
    "bus_factor": "When discussing bus_factor, explain it carefully, do not treat a high value as a risk by default, and compare it with contributor count.",
    "open_issues": "When interpreting open issue count, describe it as a relative maintenance pressure signal and avoid treating the raw number alone as definitive evidence.",
    "documentation": "When suggesting documentation improvements, link them to concrete evidence such as README limitations, open issues, or missing governance signals.",
    "actionability": "Make suggestions specific, actionable, and tied to observed metrics.",
}


CANONICAL_ORDER = [
    "response_time",
    "bus_factor",
    "open_issues",
    "documentation",
    "actionability",
]


def load_report_reflection_memory() -> str:
    """Load saved reflection memory for the LLM report generator."""
    if not REFLECTION_MEMORY_PATH.exists():
        return ""

    return REFLECTION_MEMORY_PATH.read_text(encoding="utf-8-sig").strip()


def _detect_lesson_category(text: str) -> str | None:
    """Detect whether a memory line belongs to a known reusable lesson category."""
    lower_text = text.lower()

    if (
        "response time" in lower_text
        or "issue_response_time" in lower_text
        or "change_request_response_time" in lower_text
        or "quantile" in lower_text
    ):
        return "response_time"

    if "bus factor" in lower_text or "bus_factor" in lower_text:
        return "bus_factor"

    if (
        "open issue" in lower_text
        or "open_issues" in lower_text
        or "maintenance pressure" in lower_text
        or "backlog" in lower_text
    ):
        return "open_issues"

    if "documentation" in lower_text or "readme" in lower_text or "governance" in lower_text:
        return "documentation"

    if "actionable" in lower_text or "specific" in lower_text:
        return "actionability"

    return None


def _generalize_suggestion(suggestion: str) -> list[str]:
    """Convert project-specific reviewer suggestions into reusable lessons."""
    text = suggestion.strip()

    if not text:
        return []

    if "no changes needed" in text.lower():
        return []

    category = _detect_lesson_category(text)

    if category:
        return [CANONICAL_LESSONS[category]]

    return [text]


def _compact_memory_lines(lines: list[str]) -> list[str]:
    """Deduplicate and compact memory lines before applying the max item limit."""
    seen_categories: set[str] = set()
    custom_lines: list[str] = []

    for raw_line in lines:
        line = raw_line.strip()

        if not line.startswith("- "):
            continue

        lesson_text = line[2:].strip()
        category = _detect_lesson_category(lesson_text)

        if category:
            seen_categories.add(category)
        elif line not in custom_lines:
            custom_lines.append(line)

    compacted_lines: list[str] = []

    for category in CANONICAL_ORDER:
        if category in seen_categories:
            compacted_lines.append(f"- {CANONICAL_LESSONS[category]}")

    for line in custom_lines:
        if line not in compacted_lines:
            compacted_lines.append(line)

    if len(compacted_lines) <= MAX_MEMORY_ITEMS:
        return compacted_lines

    important_lines = [
        line
        for line in compacted_lines
        if _detect_lesson_category(line)
    ]
    other_lines = [
        line
        for line in compacted_lines
        if not _detect_lesson_category(line)
    ]

    remaining_slots = max(MAX_MEMORY_ITEMS - len(important_lines), 0)
    return important_lines + other_lines[-remaining_slots:]


def save_report_reflection_suggestions(suggestions: list[str]) -> None:
    """Save reviewer suggestions as reusable reflection memory.

    The memory stores generalized lessons, compacts similar items,
    deduplicates repeated items, and keeps at most MAX_MEMORY_ITEMS lessons.
    """
    if not suggestions:
        return

    existing_text = load_report_reflection_memory()
    all_lines: list[str] = []

    if existing_text:
        for line in existing_text.splitlines():
            line = line.strip()
            if line.startswith("- ") and line not in all_lines:
                all_lines.append(line)

    for suggestion in suggestions:
        for lesson in _generalize_suggestion(suggestion):
            line = f"- {lesson}"

            if line not in all_lines:
                all_lines.append(line)

    compacted_lines = _compact_memory_lines(all_lines)

    if not compacted_lines:
        return

    REFLECTION_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)

    final_text = "# Report Reflection Memory\n\n" + "\n".join(compacted_lines) + "\n"
    REFLECTION_MEMORY_PATH.write_text(final_text, encoding="utf-8")


if __name__ == "__main__":
    save_report_reflection_suggestions(
        [
            "The report could explicitly mention the metric open_issues when discussing maintenance backlog risk.",
            "Consider clarifying that the bus factor is a high value and should be compared with contributor count.",
            "Make the documentation suggestion more actionable.",
        ]
    )

    print(load_report_reflection_memory())
