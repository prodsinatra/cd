"""Canary token / honeytoken detection layer.

Watches for any mention of deception-technology terminology or common
OSINT-tool names in incoming results. A hit here is high-signal: legitimate
queries rarely touch these strings, so the engine treats matches as a
strong indicator someone is poking at planted bait.
"""

from __future__ import annotations

CANARY_KEYWORDS: tuple[str, ...] = (
    "honeytoken",
    "honey token",
    "canary token",
    "canarytoken",
    "decoy document",
    "tripwire file",
    "deception token",
)

OSINT_TOOL_NAMES: tuple[str, ...] = (
    "theharvester",
    "maltego",
    "spiderfoot",
    "shodan",
    "crt.sh",
    "amass",
    "recon-ng",
    "sherlock",
    "holehe",
)


def detect_canary_touch(text: str) -> dict[str, list[str]] | None:
    """Return a dict of matched canary/OSINT terms, or None if nothing hit.

    Matching is case-insensitive substring. The dict separates planted-bait
    hits from tool-name hits so the alert can be tuned accordingly.
    """
    if not text:
        return None

    lowered = text.lower()
    canary_hits = [kw for kw in CANARY_KEYWORDS if kw in lowered]
    tool_hits = [kw for kw in OSINT_TOOL_NAMES if kw in lowered]

    if not canary_hits and not tool_hits:
        return None

    result: dict[str, list[str]] = {}
    if canary_hits:
        result["canary_terms"] = canary_hits
    if tool_hits:
        result["osint_tools"] = tool_hits
    return result
