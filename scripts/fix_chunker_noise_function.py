from pathlib import Path
import re

path = Path("app/rag/chunker.py")
text = path.read_text(encoding="utf-8")

new_function = '''def is_noise_chunk(content: str, heading_path: str) -> bool:
    """Return True if this chunk is obvious webpage or API noise."""
    text = (heading_path + chr(10) + content).lower()

    cookie_noise_keywords = [
        "privacy overview",
        "cookielawinfo",
        "gdpr cookie consent",
        "functional cookies",
        "performance cookies",
        "analytical cookies",
        "advertisement cookies",
        "uncategorized cookies",
        "cookie is set by",
        "this cookie is used to",
    ]

    for keyword in cookie_noise_keywords:
        if keyword in text:
            return True

    github_endpoint_noise_keywords = [
        "create an organization repository",
        "parameters for \\"create an organization repository\\"",
        "create a repository for the authenticated user",
        "parameters for \\"create a repository for the authenticated user\\"",
        "update a repository",
        "parameters for \\"update a repository\\"",
        "delete a repository",
        "transfer a repository",
        "replace all repository topics",
        "list repository activities",
        "parameters for \\"list repository activities\\"",
        "list repositories for the authenticated user",
        "parameters for \\"list repositories for the authenticated user\\"",
    ]

    for keyword in github_endpoint_noise_keywords:
        if keyword in text:
            return True

    if "parameters for" in text:
        useful_github_fields = [
            "stargazers_count",
            "forks_count",
            "open_issues_count",
            "license",
            "readme",
        ]

        if not any(field in text for field in useful_github_fields):
            return True

    return False
'''

pattern = re.compile(
    r"^def is_noise_chunk\(.*?(?=^def |\Z)",
    flags=re.DOTALL | re.MULTILINE,
)

if not pattern.search(text):
    raise SystemExit("ERROR: def is_noise_chunk was not found")

text = pattern.sub(new_function + "\n\n", text, count=1)

path.write_text(text, encoding="utf-8")

print("OK: fixed is_noise_chunk")
