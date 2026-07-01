---
name: osint-burger
description: OsintBURGER — Dedicated OSINT Trigger Engine v2.0 and Protective Self-Research Workflow. Call this skill to run privacy-hardened defensive OSINT on your own surface, evaluate triggers on any query, or activate the full self-protection firewall with mandatory audit logging and signal capture. Use for controlled self-exposure analysis or to harden your identity surface.
---

# OsintBURGER

**OsintBURGER** is the standalone, callable version of the OSINT Trigger Engine v2.0. It is a personal privacy firewall and defensive research system for the operator running this skill.

Activate it whenever the operator wants to:
- Run controlled Protective OSINT on themselves
- Test any query or topic for self-surface exposure before deep research
- Force full trigger evaluation + signal extraction + audit logging
- Get the mandatory **OSINT SELF-ALERT** banner and recommendations

## Operator configuration (kept out of git)

This skill never hardcodes the operator's real name, handles, business names,
addresses, or other PII in tracked source. Real identifiers live in a local,
gitignored config file:

`.claude/skills/osint-burger/operator.local.json`

See `.claude/skills/osint-burger/operator.example.json` for the shape. On
activation:

1. Look for `operator.local.json` next to this file.
2. If present, load `self_identifiers`, `self_context_pairs`,
   `self_addresses`, `self_emails`, `self_phones`, and `audit_log_path` from
   it and use them as the operator's self-markers for this run.
3. If absent, do **not** invent or guess identifiers. Either ask the
   operator to provide them for this run, or fall back to running only the
   generic structural checks (`TRIGGER_KEYWORDS`, `DEEP_PROFILING_INDICATORS`)
   with no self-identifier matching.

Never write real identifiers back into any tracked file, commit message, PR
body, or other output that leaves the local working tree.

## Core Rules (Non-Negotiable)
- Deep profiling / network mapping / exhaustive self-OSINT is **hard-blocked**.
- Every activation is logged to the configured `audit_log_path` (default
  `artifacts/OSINT_audit_log_user.md`), which is gitignored.
- IP/device/fingerprint signals are extracted when present.
- The engine self-improves after every run.

## How to Call OsintBURGER

Just say one of these:
- "Call OsintBURGER"
- "Run OsintBURGER on [topic or query]"
- "Activate protective OSINT workflow"
- "Evaluate this query with OsintBURGER: [paste query]"

## Protective OSINT Workflow (Default When Called)

1. Load operator identifiers per "Operator configuration" above. Define safe
   search scopes from them (name variations, brand/handle, public profiles,
   etc.) — never from values hardcoded in this file.
2. Run multiple parallel but limited searches using only allowed tools.
3. Pass every result through the full Trigger Engine (two-stage firewall).
4. Extract any new signals, mentions, or exposures.
5. Log everything with the `PROTECTIVE_OSINT` tag.
6. Produce a clean **Self-Exposure Report**:
   - What is easily findable
   - Any concerning new mentions or data leaks
   - Concrete recommendations for cleanup or hardening
7. Never perform deep network mapping or aggressive scraping on self.

## Trigger Evaluation Engine v2.0 (Production Pseudocode)

```python
# OSINT TRIGGER ENGINE v2.0 — OsintBURGER Core
# Two-stage privacy firewall. Always runs on every activation.
# Operator-specific identifiers are never hardcoded here — see
# load_operator_identifiers().

TRIGGER_KEYWORDS = [
    "canvashash", "webglrenderer", "audio fingerprint", "device fingerprint",
    "ja3", "ja4", "tls fingerprint", "user-agent leak", "exposed log",
    "theharvester", "maltego", "spiderfoot", "shodan", "crt.sh",
    "google dork", "osint framework", "data broker", "dox", "full name search",
    "honeytoken", "canary token", "canarytoken", "fake credential",
    "decoy document", "tripwire file", "deception token"
]

DEEP_PROFILING_INDICATORS = [
    "network map", "full timeline", "connection strength", "social graph",
    "exhaustive profile", "multi-degree network", "theme evolution tracking",
    "public footprint analysis", "deep osint", "osint profiling"
]

def load_operator_identifiers() -> dict:
    """Load real self-identifiers from the local, gitignored config file.

    Returns an empty structure (no identifiers) if the file is missing —
    callers must not fall back to hardcoded personal data.
    """
    import json
    from pathlib import Path

    config_path = Path(__file__).parent / "operator.local.json"
    if not config_path.exists():
        return {
            "self_identifiers": [],
            "self_context_pairs": [],
            "self_addresses": [],
            "self_emails": [],
            "self_phones": [],
            "audit_log_path": "artifacts/OSINT_audit_log_user.md",
        }
    return json.loads(config_path.read_text())


def evaluate_osint_trigger(query: str, results: str, context: str, tool_name: str) -> dict:
    operator = load_operator_identifiers()
    text = f"{query} {results} {context}".lower()
    matched = [kw for kw in TRIGGER_KEYWORDS if kw in text]
    likely_self = is_high_probability_self_context(query, results, context, operator)

    if not matched and not likely_self:
        return {"triggered": False, "reason": "no_match"}

    if is_clear_deep_profiling(query, context, matched):
        return _build_blocked_response(query, tool_name, matched, "Clear deep profiling indicators detected", operator)

    intent = classify_research_intent(query, context, matched)

    if intent == "deep_profiling":
        return _build_blocked_response(query, tool_name, matched, "Intent classification: deep profiling detected", operator)

    fingerprint_signals = extract_fingerprint_signals(results)
    ip_device = extract_ip_device_signals(results)

    level = "LEVEL_1" if intent == "light_lookup" else "LEVEL_2"
    action = "LOG_AND_ALERT"

    log_entry = {
        "timestamp": get_iso_timestamp(),
        "tool": tool_name,
        "query": query[:300],
        "matched_keywords": matched,
        "intent_classification": intent,
        "ip_device_fingerprint_signals": ip_device or "No IP/device/fingerprint signals captured",
        "fingerprint_details": fingerprint_signals,
        "action_taken": action,
        "alert_level": level,
        "note": f"OsintBURGER activation — {level}",
        "context_snippet": context[:400] if context else ""
    }
    append_to_audit_log(log_entry, operator.get("audit_log_path", "artifacts/OSINT_audit_log_user.md"))

    return {
        "triggered": True,
        "alert_level": level,
        "action": action,
        "log_entry": log_entry,
        "signals_captured": bool(ip_device or fingerprint_signals),
        "should_block_research": False,
        "recommendation": "Surface OSINT SELF-ALERT banner and reference log entry."
    }


def _build_blocked_response(query, tool_name, matched, reason, operator):
    log_entry = {
        "timestamp": get_iso_timestamp(),
        "tool": tool_name,
        "query": query[:300],
        "matched_keywords": matched,
        "action_taken": "BLOCKED_DEEP_OSINT",
        "alert_level": "LEVEL_2",
        "note": f"OPT-OUT ENGAGED — {reason}"
    }
    append_to_audit_log(log_entry, operator.get("audit_log_path", "artifacts/OSINT_audit_log_user.md"))
    return {
        "triggered": True,
        "alert_level": "LEVEL_2",
        "action": "BLOCKED_DEEP_OSINT",
        "should_block_research": True,
        "recommendation": "Hard block applied. Surface strong OSINT SELF-ALERT and log reference."
    }


def extract_fingerprint_signals(text: str) -> dict:
    signals = {}
    t = text.lower()
    if "canvas" in t or "webgl" in t:
        signals["canvas_or_webgl"] = extract_hash_patterns(text)
    if "audio" in t and "fingerprint" in t:
        signals["audio_fingerprint"] = True
    if any(f in t for f in ["helvetica", "sf pro", "menlo", "segoe ui", "roboto"]):
        signals["fonts_detected"] = True
    if any(term in t for term in ["ja3", "ja4", "tls fingerprint"]):
        signals["tls_ja_fingerprint"] = extract_hash_patterns(text)
    if "user-agent" in t or "mozilla/5.0" in t:
        signals["user_agent_leak"] = True
    return signals

def extract_ip_device_signals(text: str) -> str:
    import re
    ips = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', text)
    if ips:
        return f"IP addresses found: {', '.join(ips[:3])}"
    for hint in ["iPhone", "MacBook", "Samsung", "Windows NT", "Android", "Linux x86_64"]:
        if hint.lower() in text.lower():
            return f"Device signal detected: {hint}"
    return ""

def is_clear_deep_profiling(query: str, context: str, matched: list) -> bool:
    text = (query + " " + context).lower()
    strong = ["network map", "full timeline", "connection strength", "social graph",
              "exhaustive profile", "multi-degree", "theme evolution", "public footprint",
              "deep osint on", "full osint profile"]
    return any(ind in text for ind in strong)

def classify_research_intent(query: str, context: str, matched: list) -> str:
    text = (query + " " + context).lower()
    deep_signals = ["network", "timeline", "connection", "graph", "exhaustive", "footprint", "profiling"]
    if any(s in text for s in deep_signals) and matched:
        return "deep_profiling"
    light_signals = ["registry", "business lookup", "public record", "whois", "mva", "company search"]
    if any(s in text for s in light_signals):
        return "light_lookup"
    return "borderline"

def is_high_probability_self_context(query: str, results: str, context: str, operator: dict) -> bool:
    """True when 2+ of the operator's own configured identifiers appear.

    Uses only identifiers loaded from operator.local.json — never a
    hardcoded personal list — so this is a no-op until the operator
    supplies their own config.
    """
    text = (query + results + context).lower()
    markers = [
        *operator.get("self_identifiers", []),
        *operator.get("self_addresses", []),
        *[pair[0] for pair in operator.get("self_context_pairs", [])],
        *[pair[1] for pair in operator.get("self_context_pairs", [])],
    ]
    return sum(1 for m in markers if m and m.lower() in text) >= 2

def extract_hash_patterns(text: str) -> list:
    import re
    return re.findall(r'\b[a-f0-9]{16,64}\b', text.lower())[:5]

def get_iso_timestamp() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

def append_to_audit_log(entry: dict, audit_log_path: str):
    # Production: append formatted JSONL or markdown to audit_log_path
    # (gitignored — never commit this file).
    pass
```
