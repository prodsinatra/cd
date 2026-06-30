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

# Street pattern: a house number, up to 4 name words, then a street suffix.
STREET_RE = re.compile(
    r"\b\d{1,5}\s+(?:[A-Za-z0-9.'-]+\s+){0,4}"
    r"(?:street|st|avenue|ave|boulevard|blvd|road|rd|lane|ln|drive|dr|"
    r"way|place|pl|court|ct|plaza|plz|terrace|ter|highway|hwy|parkway|pkwy)"
    r"\.?\b",
    re.IGNORECASE,
)

# Postal codes only match when preceded by a context word — bare 5-digit
# numbers are too noisy (years, IDs, prices, etc).
POSTAL_CONTEXT_RE = re.compile(
    r"(?:\b(?:zip|zipcode|postal[\s_-]?code|postcode|post[\s_-]?code)\b)[\s:#-]*"
    r"([A-Z0-9][A-Z0-9 \-]{2,9}[A-Z0-9])",
    re.IGNORECASE,
)

EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# NANP phones with at least one separator, paren, or +1 prefix — avoids
# matching bare 10-digit IDs.
PHONE_RE = re.compile(
    r"(?:\+?1[-.\s])?"
    r"(?:\(\d{3}\)\s?|\d{3}[-.\s])"
    r"\d{3}[-.\s]"
    r"\d{4}\b"
)

# Decimal lat/lng pair, both with 4+ fractional digits (skips integer-ish
# comma-separated number pairs).
GEO_RE = re.compile(
    r"-?\d{1,2}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}"
)

# Six octet MAC, colon- or dash-separated.
MAC_RE = re.compile(
    r"\b[0-9a-fA-F]{2}(?:[:-][0-9a-fA-F]{2}){5}\b"
)

NO_IP_MARKER = "No IP/device signals captured"
NO_FP_MARKER = "No fingerprint signals captured"
NO_PII_MARKER = "No PII signals captured"


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


def extract_address_signals(results_text: str) -> Union[dict, str]:
    """Find street addresses + context-anchored postal codes.

    Returns a dict with optional keys "streets" and "postal_codes", or
    NO_PII_MARKER if nothing matched.
    """
    if not results_text:
        return NO_PII_MARKER

    streets = _unique_preserving_order(
        m.group(0).strip() for m in STREET_RE.finditer(results_text)
    )
    postals = _unique_preserving_order(
        m.group(1).strip() for m in POSTAL_CONTEXT_RE.finditer(results_text)
    )

    out: dict[str, list[str]] = {}
    if streets:
        out["streets"] = streets
    if postals:
        out["postal_codes"] = postals
    return out if out else NO_PII_MARKER


def extract_email_signals(results_text: str) -> Union[dict, str]:
    if not results_text:
        return NO_PII_MARKER
    hits = _unique_preserving_order(EMAIL_RE.findall(results_text))
    return {"emails": hits} if hits else NO_PII_MARKER


def extract_phone_signals(results_text: str) -> Union[dict, str]:
    if not results_text:
        return NO_PII_MARKER
    hits = _unique_preserving_order(
        m.group(0) for m in PHONE_RE.finditer(results_text)
    )
    return {"phones": hits} if hits else NO_PII_MARKER


def extract_geo_signals(results_text: str) -> Union[dict, str]:
    if not results_text:
        return NO_PII_MARKER
    hits = _unique_preserving_order(
        m.group(0) for m in GEO_RE.finditer(results_text)
    )
    return {"coordinates": hits} if hits else NO_PII_MARKER


def extract_mac_signals(results_text: str) -> Union[dict, str]:
    if not results_text:
        return NO_PII_MARKER
    hits = _unique_preserving_order(
        m.group(0) for m in MAC_RE.finditer(results_text)
    )
    return {"mac_addresses": hits} if hits else NO_PII_MARKER


def extract_pii_signals(results_text: str) -> Union[dict, str]:
    """Aggregate every PII extractor into one structured dict.

    Returns a dict keyed by category (address, email, phone, geo, mac), or
    NO_PII_MARKER if no extractor matched. Categories that didn't match are
    omitted so the audit log stays compact.
    """
    if not results_text:
        return NO_PII_MARKER

    bundle: dict[str, dict] = {}
    for category, fn in (
        ("address", extract_address_signals),
        ("email", extract_email_signals),
        ("phone", extract_phone_signals),
        ("geo", extract_geo_signals),
        ("mac", extract_mac_signals),
    ):
        out = fn(results_text)
        if isinstance(out, dict):
            bundle[category] = out
    return bundle if bundle else NO_PII_MARKER


def detect_self_pii_leak(results_text: str, config) -> Union[dict, None]:
    """Return matches of operator-configured PII appearing in results.

    This is the high-signal "your own data leaked" detector: if any of the
    operator's configured addresses, emails, or phones appears in the
    incoming results blob, that scope is logged regardless of whether the
    query targeted them. Phone matching is digit-normalized so formatting
    differences don't hide a leak.
    """
    if not results_text:
        return None

    lowered = results_text.lower()
    digits_only_results = "".join(ch for ch in results_text if ch.isdigit())

    hits: dict[str, list[str]] = {}

    for category, values in (
        ("addresses", getattr(config, "self_addresses", [])),
        ("emails", getattr(config, "self_emails", [])),
    ):
        matched = [v for v in values if v and v.lower() in lowered]
        if matched:
            hits[category] = matched

    matched_phones: list[str] = []
    for phone in getattr(config, "self_phones", []) or []:
        if not phone:
            continue
        digits = "".join(ch for ch in phone if ch.isdigit())
        if phone.lower() in lowered:
            matched_phones.append(phone)
        elif digits and digits in digits_only_results:
            matched_phones.append(phone)
    if matched_phones:
        hits["phones"] = matched_phones

    return hits if hits else None


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
