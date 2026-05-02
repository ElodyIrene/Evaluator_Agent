from pathlib import Path
import asyncio
import json
import re
import yaml
from bs4 import BeautifulSoup
from markdownify import markdownify as to_markdown
from playwright.async_api import async_playwright

INDEX_PATH = Path("knowledge_base/indexes/metric_sources.yaml")
RAW_ROOT = Path("knowledge_base/raw_sources")
RENDERED_ROOT = Path("knowledge_base/rendered_sources")
PROCESSED_ROOT = Path("knowledge_base/processed_sources")


def q(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


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
        or soup.find("div", class_=lambda value: value and "markdown" in " ".join(value if isinstance(value, list) else [value]).lower())
        or soup.body
        or soup
    )


def collect_opendigger_sources(index_data: dict) -> list[dict]:
    metrics = index_data.get("metrics", {})
    results = []
    seen_paths = set()

    for metric_id, metric_info in metrics.items():
        for source_key in ["primary_source", "secondary_source"]:
            source = metric_info.get(source_key)
            if not source:
                continue

            url = source.get("url", "")
            raw_path = source.get("local_raw_path", "")

            if "open-digger.cn" not in url:
                continue

            if not url or not raw_path:
                continue

            if raw_path in seen_paths:
                continue

            seen_paths.add(raw_path)

            results.append(
                {
                    "metric_id": metric_id,
                    "source_key": source_key,
                    "title": source.get("title", ""),
                    "url": url,
                    "raw_path": raw_path,
                }
            )

    return results


def output_paths(raw_path_text: str) -> tuple[Path, Path]:
    raw_path = Path(raw_path_text)
    relative = raw_path.relative_to(RAW_ROOT)
    rendered_path = RENDERED_ROOT / relative
    processed_path = PROCESSED_ROOT / relative.with_suffix(".md")
    return rendered_path, processed_path


async def render_one(page, source: dict) -> dict:
    rendered_path, processed_path = output_paths(source["raw_path"])

    print()
    print(f"Rendering: {source['metric_id']}")
    print(f"URL: {source['url']}")

    await page.goto(source["url"], wait_until="networkidle", timeout=60000)

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
            text_body = await page.locator("main").inner_text(timeout=5000)
        except Exception:
            text_body = await page.locator("body").inner_text(timeout=5000)

        markdown_body = clean_markdown(text_body)

    front_matter = "\n".join(
        [
            "---",
            f"metric_id: {q(source['metric_id'])}",
            f"source_key: {q(source['source_key'])}",
            f"source_title: {q(source['title'])}",
            f"source_url: {q(source['url'])}",
            f"rendered_html_path: {q(str(rendered_path).replace(chr(92), '/'))}",
            f"raw_html_path: {q(source['raw_path'])}",
            "---",
            "",
        ]
    )

    processed_path.parent.mkdir(parents=True, exist_ok=True)
    processed_path.write_text(front_matter + markdown_body, encoding="utf-8")

    result = {
        "metric_id": source["metric_id"],
        "url": source["url"],
        "processed_path": str(processed_path).replace("\\", "/"),
        "rendered_path": str(rendered_path).replace("\\", "/"),
        "char_count": len(markdown_body),
    }

    print(f"[OK] {processed_path} chars={len(markdown_body)}")

    return result


async def main() -> None:
    if not INDEX_PATH.exists():
        raise FileNotFoundError(f"Missing index file: {INDEX_PATH}")

    index_data = yaml.safe_load(INDEX_PATH.read_text(encoding="utf-8-sig"))
    sources = collect_opendigger_sources(index_data)

    print(f"Found {len(sources)} OpenDigger source pages.")

    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for source in sources:
            result = await render_one(page, source)
            results.append(result)

        await browser.close()

    bad = [row for row in results if row["char_count"] < 300]

    print()
    print("Render summary")
    print("--------------")
    print(f"Total: {len(results)}")
    print(f"Too small: {len(bad)}")

    if bad:
        for row in bad:
            print(f"[SMALL] {row['processed_path']} chars={row['char_count']}")
        raise SystemExit("ERROR: some rendered Markdown files are still too small")

    print("OK: OpenDigger Markdown files were regenerated.")


if __name__ == "__main__":
    asyncio.run(main())
