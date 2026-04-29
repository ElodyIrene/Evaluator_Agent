from app.schemas import EvaluationState
from app.tools.github_client import get_project_basic_info, parse_github_url


def project_parser_agent(state: EvaluationState) -> EvaluationState:
    """Parse GitHub URL and fetch basic project information."""
    repo_input = parse_github_url(state.input_url)

    basic_info = get_project_basic_info(
        owner=repo_input.owner,
        repo=repo_input.repo,
    )

    state.owner = repo_input.owner
    state.repo = repo_input.repo
    state.basic_info = basic_info

    return state


if __name__ == "__main__":
    state = EvaluationState(
        input_url="https://github.com/langchain-ai/langgraph"
    )

    result = project_parser_agent(state)

    print("owner:", result.owner)
    print("repo:", result.repo)
    print("name:", result.basic_info.name if result.basic_info else None)
    print("stars:", result.basic_info.stars if result.basic_info else None)
    print("language:", result.basic_info.language if result.basic_info else None)
    print("readme exists:", bool(result.basic_info.readme) if result.basic_info else False)
