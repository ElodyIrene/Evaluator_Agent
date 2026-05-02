from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import time
import yaml

INDEX_PATH = Path("knowledge_base/indexes/metric_sources.yaml")


def download(url: str, output_path: Path, retries: int = 2) -> bool:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, retries + 1):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": "Evaluator-Agent-KnowledgeBase/0.1"
                },
            )

            with urlopen(request, timeout=30) as response:
                content = response.read()

            if len(content) < 100:
                print(f"[WARN] Very small file: {output_path} ({len(content)} bytes)")

            output_path.write_bytes(content)
            print(f"[OK] Saved: {output_path}")
            return True

        except (HTTPError, URLError, TimeoutError) as error:
            print(f"[WARN] Attempt {attempt} failed: {url}")
            print(f"       Reason: {error}")
            time.sleep(1)

    print(f"[FAIL] Could not download: {url}")
    return False


def collect_sources(metrics: dict) -> list[dict]:
    sources = []
    seen_paths = set()

    for metric_id, metric_info in metrics.items():
        for source_key in ["primary_source", "secondary_source"]:
            source = metric_info.get(source_key)
            if not source:
                continue

            url = source.get("url")
            local_raw_path = source.get("local_raw_path")
            title = source.get("title", "")

            if not url or not local_raw_path:
                continue

            if local_raw_path in seen_paths:
                continue

            seen_paths.add(local_raw_path)

            sources.append(
                {
                    "metric_id": metric_id,
                    "source_key": source_key,
                    "title": title,
                    "url": url,
                    "local_raw_path": local_raw_path,
                }
            )

    return sources


def main() -> None:
    if not INDEX_PATH.exists():
        raise FileNotFoundError(f"Missing index file: {INDEX_PATH}")

    data = yaml.safe_load(INDEX_PATH.read_text(encoding="utf-8-sig"))
    metrics = data.get("metrics", {})

    sources = collect_sources(metrics)

    print(f"Found {len(sources)} source documents to download.")

    failed = []

    for item in sources:
        print()
        print(f"Metric: {item['metric_id']}")
        print(f"Source: {item['title']}")
        print(f"URL: {item['url']}")

        ok = download(item["url"], Path(item["local_raw_path"]))

        if not ok:
            failed.append(item)

        time.sleep(0.5)

    print()
    print("Download summary")
    print("----------------")
    print(f"Total: {len(sources)}")
    print(f"Failed: {len(failed)}")

    if failed:
        print()
        print("Failed sources:")
        for item in failed:
            print(f"- {item['metric_id']}: {item['url']}")
        raise SystemExit(1)

    print("OK: all source documents were downloaded.")


if __name__ == "__main__":
    main()
