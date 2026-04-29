import base64
import re
from typing import Any

import httpx

from app.config import settings
from app.schemas import ProjectBasicInfo, RepoInput


GITHUB_URL_PATTERN = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)


def parse_github_url(url: str) -> RepoInput:
    """Parse a GitHub repository URL into owner and repo."""
    match = GITHUB_URL_PATTERN.match(url.strip())

    if not match:
        raise ValueError(
            "Invalid GitHub repository URL. Example: https://github.com/langchain-ai/langgraph"
        )

    owner = match.group("owner")
    repo = match.group("repo")

    return RepoInput(url=url, owner=owner, repo=repo)


def _github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    return headers


def _get_json(url: str) -> dict[str, Any]:
    response = httpx.get(url, headers=_github_headers(), timeout=20)
    response.raise_for_status()
    return response.json()


def get_readme(owner: str, repo: str) -> str | None:
    """Fetch README content from GitHub."""
    url = f"https://api.github.com/repos/{owner}/{repo}/readme"

    try:
        data = _get_json(url)
    except httpx.HTTPStatusError:
        return None

    content = data.get("content")
    encoding = data.get("encoding")

    if not content or encoding != "base64":
        return None

    return base64.b64decode(content).decode("utf-8", errors="ignore")


def get_project_basic_info(owner: str, repo: str) -> ProjectBasicInfo:
    """Fetch basic repository information from GitHub."""
    url = f"https://api.github.com/repos/{owner}/{repo}"
    data = _get_json(url)

    license_data = data.get("license") or {}

    return ProjectBasicInfo(
        owner=owner,
        repo=repo,
        name=data.get("name", repo),
        description=data.get("description"),
        stars=data.get("stargazers_count", 0),
        forks=data.get("forks_count", 0),
        open_issues=data.get("open_issues_count", 0),
        language=data.get("language"),
        topics=data.get("topics", []),
        license=license_data.get("spdx_id"),
        readme=get_readme(owner, repo),
    )


if __name__ == "__main__":
    example_url = "https://github.com/langchain-ai/langgraph"
    repo_input = parse_github_url(example_url)
    info = get_project_basic_info(repo_input.owner, repo_input.repo)

    print("owner:", info.owner)
    print("repo:", info.repo)
    print("name:", info.name)
    print("stars:", info.stars)
    print("forks:", info.forks)
    print("language:", info.language)
    print("license:", info.license)
    print("topics:", info.topics[:5])
    print("readme exists:", bool(info.readme))
