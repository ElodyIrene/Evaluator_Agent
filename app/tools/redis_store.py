import json
from datetime import UTC, datetime
from typing import Any

import redis

from app.config import settings


REPORT_HISTORY_KEY = "report_history"
TASK_STATE_TTL_SECONDS = 60 * 60 * 24


def get_redis_client() -> redis.Redis:
    """Create a Redis client with short timeout.

    Redis is optional for the main evaluation flow.
    If Redis is unavailable, it should fail fast instead of blocking the API.
    """
    return redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
        retry_on_timeout=False,
    )


def ping_redis() -> bool:
    """Check whether Redis is available."""
    client = get_redis_client()
    return bool(client.ping())


def save_json(
    key: str,
    value: dict[str, Any],
    expire_seconds: int | None = None,
) -> None:
    """Save a dictionary as JSON into Redis."""
    client = get_redis_client()
    client.set(
        key,
        json.dumps(value, ensure_ascii=False),
        ex=expire_seconds,
    )


def load_json(key: str) -> dict[str, Any] | None:
    """Load a JSON dictionary from Redis."""
    client = get_redis_client()
    value = client.get(key)

    if value is None:
        return None

    return json.loads(value)


def delete_key(key: str) -> None:
    """Delete a Redis key."""
    client = get_redis_client()
    client.delete(key)


def _report_key(owner: str, repo: str) -> str:
    return f"report:{owner}:{repo}"


def save_report(
    owner: str,
    repo: str,
    report: dict[str, Any],
) -> None:
    """Save an evaluation report and add it to recent history."""
    client = get_redis_client()
    key = _report_key(owner, repo)

    value = {
        "owner": owner,
        "repo": repo,
        "saved_at": datetime.now(UTC).isoformat(),
        "report": report,
    }

    save_json(key, value)

    client.lrem(REPORT_HISTORY_KEY, 0, key)
    client.lpush(REPORT_HISTORY_KEY, key)
    client.ltrim(REPORT_HISTORY_KEY, 0, 19)


def load_report(owner: str, repo: str) -> dict[str, Any] | None:
    """Load the latest saved report for a repository."""
    return load_json(_report_key(owner, repo))


def list_recent_reports(limit: int = 10) -> list[dict[str, Any]]:
    """List recent saved reports."""
    client = get_redis_client()
    keys = client.lrange(REPORT_HISTORY_KEY, 0, limit - 1)

    reports: list[dict[str, Any]] = []

    for key in keys:
        value = load_json(key)

        if value is not None:
            reports.append(value)

    return reports


def _task_state_key(task_id: str) -> str:
    return f"task_state:{task_id}"


def save_task_state(
    task_id: str,
    state: dict[str, Any],
    expire_seconds: int = TASK_STATE_TTL_SECONDS,
) -> None:
    """Save workflow task state."""
    value = {
        "task_id": task_id,
        "saved_at": datetime.now(UTC).isoformat(),
        "state": state,
    }

    save_json(
        key=_task_state_key(task_id),
        value=value,
        expire_seconds=expire_seconds,
    )


def load_task_state(task_id: str) -> dict[str, Any] | None:
    """Load workflow task state."""
    return load_json(_task_state_key(task_id))


if __name__ == "__main__":
    print("redis ping:", ping_redis())
