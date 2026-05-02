from pathlib import Path
import asyncio
import hashlib
import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from markdownify import markdownify as to_markdown
from playwright.async_api import async_playwright

PROCESSED_ROOT = Path("knowledge_base/processed_sources")
LINKED_RENDERED_ROOT = Path("knowledge_base/rendered_sources/linked_official")
LINKED_MD_ROOT = Path("knowledge_base/processed_sources/linked_official")
METRIC_DOCS_ROOT = Path("knowledge_base/metric_docs")
INDEX_ROOT = Path("knowledge_base/indexes")

DISCOVERED_LINKS_PATH = INDEX_ROOT / "discovered_official_links.jsonl"
METRIC_DOC_INDEX_PATH = INDEX_ROOT / "metric_doc_index.json"

OFFICIAL_LINK_DOMAINS = [
    "chaoss.community",
]


def parse_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    raw_meta = parts[1]
    body = parts[2].strip()

    meta = {}

    for line in raw_meta.splitlines():
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        meta[key] = value

    return meta, body


def clean_markdown(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip() + "\n"


def remove_noise(soup: BeautifulSoup) -> None:
    remove_tag_names = [
        "script",
        "style",
        "noscript",
        "svg",
        "canvas",
        "iframe",
        "form",
        "button",
        "input",
        "nav",
        "aside",
        "footer",
        "header",
    ]

    for tag_name in remove_tag_names:
        for tag in list(soup.find_all(tag_name)):
            if tag is not None:
                tag.decompose()

    noise_keywords = [
        "navbar",
        "sidebar",
        "footer",
        "menu",
        "pagination",
        "breadcrumb",
        "search",
        "doc-sidebar",
        "table-of-contents",
        "site-header",
        "site-footer",
    ]

    for tag in list(soup.find_all(True)):
        attrs = getattr(tag, "attrs", None)
        if not isinstance(attrs, dict):
            continue

        class_value = attrs.get("class", [])
        if isinstance(class_value, str):
            class_text = class_value
        elif isinstance(class_value, list):
            class_text = " ".join(str(item) for item in class_value)
        else:
            class_text = ""

        id_text = str(attrs.get("id", ""))
        combined = f"{class_text} {id_text}".lower()

        if any(keyword in combined for keyword in noise_keywords):
            tag.decompose()


def choose_main_content(soup: BeautifulSoup):
    return (
        soup.find("main")
        or soup.find("article")
        or soup.find(attrs={"role": "main"})
        or soup.body
        or soup
    )


def is_official_detail_link(url: str) -> bool:
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    return any(domain == d or domain.endswith("." + d) for d in OFFICIAL_LINK_DOMAINS)


def normalize_url(url: str) -> str:
    return url.strip().rstrip(").,;\"'")


def find_markdown_links(text: str) -> list[str]:
    pattern = re.compile(r"(?<!!)\[[^\]]+\]\((https?://[^)\s]+)\)")
    urls = []

    for match in pattern.finditer(text):
        url = normalize_url(match.group(1))
        if is_official_detail_link(url):
            urls.append(url)

    return sorted(set(urls))


def safe_filename_for_url(url: str) -> str:
    parsed = urlparse(url)
    base = f"{parsed.netloc}{parsed.path}".strip("/")
    base = re.sub(r"[^a-zA-Z0-9_-]+", "_", base)
    base = base.strip("_") or "linked_source"

    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]

    if len(base) > 90:
        base = base[:90].rstrip("_")

    return f"{base}_{digest}"


def discover_official_links() -> tuple[list[dict], dict[str, list[Path]]]:
    discovered = []
    metric_original_files = {}

    for path in sorted(PROCESSED_ROOT.rglob("*.md")):
        if "linked_official" in path.parts:
            continue

        text = path.read_text(encoding="utf-8", errors="ignore")
        meta, body = parse_front_matter(text)

        metric_id = meta.get("metric_id")
        if not metric_id:
            continue

        metric_original_files.setdefault(metric_id, []).append(path)

        urls = find_markdown_links(text)

        for url in urls:
            discovered.append(
                {
                    "metric_id": metric_id,
                    "discovered_from": str(path).replace("\\", "/"),
                    "url": url,
                }
            )

    unique = []
    seen = set()

    for item in discovered:
        key = (item["metric_id"], item["url"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    return unique, metric_original_files


async def render_and_convert_link(page, item: dict) -> dict:
    metric_id = item["metric_id"]
    url = item["url"]
    filename = safe_filename_for_url(url)

    rendered_path = LINKED_RENDERED_ROOT / f"{filename}.html"
    md_path = LINKED_MD_ROOT / f"{filename}.md"

    print()
    print(f"Rendering linked official source for metric: {metric_id}")
    print(f"URL: {url}")

    await page.goto(url, wait_until="networkidle", timeout=60000)

    try:
        await page.wait_for_selector("main, article, body", timeout=15000)
    except Exception:
        pass

    html = await page.content()

    rendered_path.parent.mkdir(parents=True, exist_ok=True)
    rendered_path.write_text(html, encoding="utf-8")

    soup = BeautifulSoup(html, "html.parser")
    remove_noise(soup)

    main_content = choose_main_content(soup)

    markdown_body = to_markdown(
        str(main_content),
        heading_style="ATX",
        bullets="-",
    )

    markdown_body = clean_markdown(markdown_body)

    if len(markdown_body) < 300:
        try:
            markdown_body = await page.locator("main").inner_text(timeout=5000)
        except Exception:
            markdown_body = await page.locator("body").inner_text(timeout=5000)

        markdown_body = clean_markdown(markdown_body)

    front_matter = "\n".join(
        [
            "---",
            f'metric_id: "{metric_id}"',
            'source_type: "linked_official_detail"',
            f'source_url: "{url}"',
            f'discovered_from: "{item["discovered_from"]}"',
            f'rendered_html_path: "{str(rendered_path).replace(chr(92), "/")}"',
            "---",
            "",
        ]
    )

    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(front_matter + markdown_body, encoding="utf-8")

    result = {
        **item,
        "processed_path": str(md_path).replace("\\", "/"),
        "rendered_html_path": str(rendered_path).replace("\\", "/"),
        "char_count": len(markdown_body),
    }

    print(f"[OK] {md_path} chars={len(markdown_body)}")

    return result


def build_merged_metric_docs(
    metric_original_files: dict[str, list[Path]],
    linked_results: list[dict],
) -> dict:
    METRIC_DOCS_ROOT.mkdir(parents=True, exist_ok=True)

    links_by_metric = {}

    for row in linked_results:
        links_by_metric.setdefault(row["metric_id"], []).append(row)

    index = {}

    all_metric_ids = sorted(set(metric_original_files) | set(links_by_metric))

    for metric_id in all_metric_ids:
        original_files = metric_original_files.get(metric_id, [])
        linked_files = links_by_metric.get(metric_id, [])

        output_path = METRIC_DOCS_ROOT / f"{metric_id}.md"

        parts = [
            f"# Metric Document: {metric_id}",
            "",
            "This file is a merged RAG-ready metric document.",
            "",
            "It combines:",
            "",
            "- the cleaned OpenDigger or GitHub source page",
            "- linked official detail pages discovered from that source",
            "",
            "## Included Source Files",
            "",
        ]

        for path in original_files:
            parts.append(f"- Original source: `{str(path).replace(chr(92), '/')}`")

        for row in linked_files:
            parts.append(f"- Linked official source: `{row['processed_path']}`")

        parts.append("")

        for i, path in enumerate(original_files, start=1):
            text = path.read_text(encoding="utf-8", errors="ignore")
            parts.extend(
                [
                    f"---",
                    f"",
                    f"## Source {i}: Original Processed Source",
                    f"",
                    f"source_file: `{str(path).replace(chr(92), '/')}`",
                    f"",
                    text.strip(),
                    "",
                ]
            )

        offset = len(original_files)

        for j, row in enumerate(linked_files, start=1):
            path = Path(row["processed_path"])
            text = path.read_text(encoding="utf-8", errors="ignore")

            parts.extend(
                [
                    f"---",
                    f"",
                    f"## Source {offset + j}: Linked Official Detail Source",
                    f"",
                    f"source_url: {row['url']}",
                    f"source_file: `{row['processed_path']}`",
                    f"",
                    text.strip(),
                    "",
                ]
            )

        output_path.write_text("\n".join(parts).strip() + "\n", encoding="utf-8")

        index[metric_id] = {
            "merged_doc_path": str(output_path).replace("\\", "/"),
            "original_sources": [str(p).replace("\\", "/") for p in original_files],
            "linked_official_sources": [
                {
                    "url": row["url"],
                    "processed_path": row["processed_path"],
                    "char_count": row["char_count"],
                }
                for row in linked_files
            ],
        }

        print(f"[MERGED] {output_path}")

    return index


async def main() -> None:
    INDEX_ROOT.mkdir(parents=True, exist_ok=True)

    discovered_links, metric_original_files = discover_official_links()

    print(f"Discovered official detail links: {len(discovered_links)}")

    with DISCOVERED_LINKS_PATH.open("w", encoding="utf-8") as f:
        for row in discovered_links:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    if not discovered_links:
        print("No linked official detail pages found.")
        linked_results = []
    else:
        linked_results = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            for item in discovered_links:
                result = await render_and_convert_link(page, item)
                linked_results.append(result)

            await browser.close()

    small = [row for row in linked_results if row["char_count"] < 300]

    if small:
        print()
        print("Small linked official documents:")
        for row in small:
            print(f"- {row['processed_path']} chars={row['char_count']}")
        raise SystemExit("ERROR: some linked official documents are still too small")

    metric_index = build_merged_metric_docs(metric_original_files, linked_results)

    METRIC_DOC_INDEX_PATH.write_text(
        json.dumps(metric_index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print("Summary")
    print("-------")
    print(f"Discovered links: {len(discovered_links)}")
    print(f"Merged metric docs: {len(metric_index)}")
    print(f"Discovered link index: {DISCOVERED_LINKS_PATH}")
    print(f"Metric doc index: {METRIC_DOC_INDEX_PATH}")
    print("OK: linked official sources were expanded and merged.")


if __name__ == "__main__":
    asyncio.run(main())
