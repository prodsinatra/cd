"""Alert banner formatter.

Designed to be parsable under low cognitive bandwidth: fixed field order,
clear labels, no decorative formatting.
"""

from __future__ import annotations

from typing import Any


def format_banner(
    *,
    level: str,
    tool: str,
    query: str,
    reason: str,
    intent: str,
    action: str,
    ip_signals: Any,
    fingerprint_signals: Any,
    canary_hits: Any = None,
    audit_ref: str | None = None,
) -> str:
    lines = [
        f"**OSINT SELF-ALERT — {level}**",
        "",
        f"Tool: {tool}",
        f"Query: {query}",
        f"Match reason: {reason}",
        f"Intent classification: {intent}",
        f"Action taken: {action}",
        f"IP/Device signals: {_render(ip_signals)}",
        f"Fingerprint signals: {_render(fingerprint_signals)}",
    ]
    if canary_hits:
        lines.append(f"Canary/OSINT-tool hits: {_render(canary_hits)}")
    if audit_ref:
        lines.append(f"Audit log entry: {audit_ref}")
    return "\n".join(lines)


def _render(value: Any) -> str:
    if value is None:
        return "None captured"
    if isinstance(value, str):
        return value
    return str(value)
