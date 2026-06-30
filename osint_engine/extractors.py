"""Signal extractors.

Pull leaked technical identifiers (IPs, device fingerprints, browser
signals) out of strings returned by upstream research tools. The engine
defensively records anything it finds so the operator can see who or what
left a trace.
"""

from __future__ import annotations

import re
from typing import Union

IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
# IPv6: matches the fully-expanded eight-group form. Compressed (::) forms
# are not in scope — leaked client IPs in logs almost always appear in full.
IPV6_RE = re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b")

FINGERPRINT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "canvas_webgl": ("canvas", "webgl"),
    "audio_fingerprint": ("audiocontext", "audio fingerprint"),
    "fonts": ("font enumeration", "installed fonts"),
    "user_agent": ("user-agent", "user agent", "useragent"),
    "tls_ja3": ("ja3", "tls fingerprint", "ja4"),
    "behavioral": ("mouse movement", "keystroke timing", "scroll pattern"),
}

NO_IP_MARKER = "No IP/device signals captured"
NO_FP_MARKER = "No fingerprint signals captured"


def extract_ip_device_signals(results_text: str) -> Union[dict, str]:
    """Find IPv4/IPv6 addresses in results text.

    Returns a dict of findings keyed by version, or NO_IP_MARKER if nothing
    matched. Duplicates are de-duplicated while preserving first-seen order.
    """
    if not results_text:
        return NO_IP_MARKER

    ipv4 = _unique_preserving_order(IPV4_RE.findall(results_text))
    ipv4 = [ip for ip in ipv4 if _is_valid_ipv4(ip)]
    ipv6 = _unique_preserving_order(
        m.group(0) for m in IPV6_RE.finditer(results_text)
    )

    found: dict[str, list[str]] = {}
    if ipv4:
        found["ipv4"] = ipv4
    if ipv6:
        found["ipv6"] = ipv6

    return found if found else NO_IP_MARKER


def extract_fingerprint_signals(results_text: str) -> Union[dict, str]:
    """Scan for browser/device fingerprinting indicators.

    Returns a dict mapping category -> excerpt around the first hit, or
    NO_FP_MARKER if nothing matched. Excerpts are small (default ±60 chars)
    so the audit log stays readable.
    """
    if not results_text:
        return NO_FP_MARKER

    lowered = results_text.lower()
    signals: dict[str, str] = {}

    for category, keywords in FINGERPRINT_KEYWORDS.items():
        for kw in keywords:
            idx = lowered.find(kw)
            if idx != -1:
                signals[category] = _snippet(results_text, idx, len(kw))
                break

    return signals if signals else NO_FP_MARKER


def _snippet(text: str, idx: int, hit_len: int, window: int = 60) -> str:
    start = max(0, idx - window)
    end = min(len(text), idx + hit_len + window)
    return text[start:end].strip()


def _unique_preserving_order(items) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _is_valid_ipv4(addr: str) -> bool:
    parts = addr.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False
