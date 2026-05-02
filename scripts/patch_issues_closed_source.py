from pathlib import Path
import yaml

path = Path("knowledge_base/indexes/metric_sources.yaml")
data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))

metrics = data["metrics"]

issues_closed = metrics["issues_closed"]

issues_closed["secondary_source"] = {
    "title": "CHAOSS - Issues Closed",
    "url": "https://chaoss.community/zh-CN/kb/metric-issues-closed",
    "local_raw_path": "knowledge_base/raw_sources/chaoss/issues_closed.html",
}

path.write_text(
    yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
    encoding="utf-8",
)

print("OK: added CHAOSS secondary source for issues_closed")
