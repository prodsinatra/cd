"""Append-only audit log.

Every trigger evaluation writes one structured entry. The file is markdown
so the operator can skim it directly; each entry is a fenced JSON block
preceded by a timestamped header.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def append_to_audit_log(
    log_path: str | Path,
    *,
    timestamp: str,
    tool: str,
    query: str,
    outcome: str,
    response: Any,
) -> None:
    """Append a single structured entry to the audit log.

    Creates parent directories as needed. Response objects that are
    dataclasses are converted to dicts before serialization.
    """
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": timestamp,
        "tool": tool,
        "query": query,
        "outcome": outcome,
        "response": _serialize(response),
    }

    header = f"\n## {timestamp} — {tool} — {outcome}\n"
    body = "```json\n" + json.dumps(entry, indent=2, default=str) + "\n```\n"

    with path.open("a", encoding="utf-8") as f:
        f.write(header)
        f.write(body)


def current_timestamp() -> str:
    """ISO-8601 UTC timestamp with second precision."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _serialize(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    return obj
