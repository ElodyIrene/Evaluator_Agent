from app.agents.project_parser import project_parser_agent
from app.schemas import EvaluationState, ProjectBasicInfo


AI_KEYWORDS = {
    "ai",
    "agent",
    "agents",
    "llm",
    "rag",
    "chatgpt",
    "openai",
    "langchain",
    "machine-learning",
    "deep-learning",
}

SDK_KEYWORDS = {
    "sdk",
    "client",
    "api-client",
    "library",
}

INFRA_KEYWORDS = {
    "database",
    "cache",
    "redis",
    "storage",
    "queue",
    "infrastructure",
}

WEB_KEYWORDS = {
    "web",
    "api",
    "fastapi",
    "django",
    "flask",
    "server",
    "backend",
}


def _contains_any(text: str, keywords: set[str]) -> bool:
    text = text.lower()
    return any(keyword in text for keyword in keywords)


def classify_project_type(basic_info: ProjectBasicInfo) -> str:
    """Classify project type using simple rules."""
    topics_text = " ".join(basic_info.topics or [])
    description = basic_info.description or ""
    readme_preview = (basic_info.readme or "")[:3000]
    language = basic_info.language or ""

    text = f"""
    {basic_info.name}
    {topics_text}
    {description}
    {readme_preview}
    {language}
    """.lower()

    if _contains_any(text, AI_KEYWORDS):
        return "AI Framework / Agent Framework"

    if _contains_any(text, SDK_KEYWORDS):
        return "SDK / Client Library"

    if _contains_any(text, INFRA_KEYWORDS):
        return "Infrastructure"

    if _contains_any(text, WEB_KEYWORDS):
        return "Web / Backend Framework"

    return "General Open Source Project"


def type_classifier_agent(state: EvaluationState) -> EvaluationState:
    """Classify the project type based on basic repository information."""
    if state.basic_info is None:
        state.errors.append("Cannot classify project type because basic_info is missing.")
        return state

    state.project_type = classify_project_type(state.basic_info)
    return state


if __name__ == "__main__":
    state = EvaluationState(
        input_url="https://github.com/langchain-ai/langgraph"
    )

    state = project_parser_agent(state)
    state = type_classifier_agent(state)

    print("owner:", state.owner)
    print("repo:", state.repo)
    print("project_type:", state.project_type)
    print("errors:", state.errors)
