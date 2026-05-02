from pathlib import Path
import json
import re
import yaml
from bs4 import BeautifulSoup
from markdownify import markdownify as to_markdown

INDEX_PATH = Path("knowledge_base/indexes/metric_sources.yaml")
RAW_ROOT = Path("knowledge_base/raw_sources")
PROCESSED_ROOT = Path("knowledge_base/processed_sources")
MANIFEST_PATH = Path("knowledge_base/processed_sources/source_manifest.jsonl")


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
        "header",
        "menu",
        "toc",
        "pagination",
        "breadcrumb",
        "search",
        "doc-sidebar",
        "table-of-contents",
    ]

    for tag in list(soup.find_all(True)):
        if tag is None:
            continue

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


def collect_sources(index_data: dict) -> list[dict]:
    metrics = index_data.get("metrics", {})
    results = []

    for metric_id, metric_info in metrics.items():
        for source_key in ["primary_source", "secondary_source"]:
            source = metric_info.get(source_key)
            if not source:
                continue

            raw_path = source.get("local_raw_path")
            url = source.get("url")
            title = source.get("title")

            if not raw_path or not url:
                continue

            results.append(
                {
                    "metric_id": metric_id,
                    "source_key": source_key,
                    "title": title or "",
                    "url": url,
                    "raw_path": raw_path,
                }
            )

    return results


def processed_path_for(raw_path: Path) -> Path:
    relative = raw_path.relative_to(RAW_ROOT)
    return PROCESSED_ROOT / relative.with_suffix(".md")


def convert_one(source: dict) -> dict:
    raw_path = Path(source["raw_path"])

    if not raw_path.exists():
        return {
            **source,
            "status": "missing_raw_file",
            "processed_path": "",
            "char_count": 0,
        }

    html = raw_path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")

    remove_noise(soup)
    main_content = choose_main_content(soup)

    markdown_body = to_markdown(
        str(main_content),
        heading_style="ATX",
        bullets="-",
    )

    markdown_body = clean_markdown(markdown_body)

    output_path = processed_path_for(raw_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    front_matter = "\n".join(
        [
            "---",
            f"metric_id: {q(source['metric_id'])}",
            f"source_key: {q(source['source_key'])}",
            f"source_title: {q(source['title'])}",
            f"source_url: {q(source['url'])}",
            f"raw_path: {q(str(raw_path).replace(chr(92), '/'))}",
            "---",
            "",
        ]
    )

    output_path.write_text(front_matter + markdown_body, encoding="utf-8")

    return {
        **source,
        "status": "ok",
        "processed_path": str(output_path).replace("\\", "/"),
        "char_count": len(markdown_body),
    }


def main() -> None:
    if not INDEX_PATH.exists():
        raise FileNotFoundError(f"Missing index file: {INDEX_PATH}")

    index_data = yaml.safe_load(INDEX_PATH.read_text(encoding="utf-8-sig"))
    sources = collect_sources(index_data)

    PROCESSED_ROOT.mkdir(parents=True, exist_ok=True)

    manifest_rows = []

    print(f"Found {len(sources)} indexed source references.")

    for source in sources:
        result = convert_one(source)
        manifest_rows.append(result)

        print(
            f"[{result['status']}] "
            f"{result['metric_id']} -> {result.get('processed_path', '')} "
            f"chars={result.get('char_count', 0)}"
        )

    with MANIFEST_PATH.open("w", encoding="utf-8") as f:
        for row in manifest_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    failed = [row for row in manifest_rows if row["status"] != "ok"]

    print()
    print("Conversion summary")
    print("------------------")
    print(f"Total references: {len(manifest_rows)}")
    print(f"Failed: {len(failed)}")
    print(f"Manifest: {MANIFEST_PATH}")

    if failed:
        raise SystemExit("ERROR: some source documents failed to convert")

    print("OK: all source documents were converted to Markdown.")


if __name__ == "__main__":
    main()
