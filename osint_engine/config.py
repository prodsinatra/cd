"""Operator-specific configuration for the trigger engine.

Self-identifiers, audit log path, and tunables live here so the engine code
stays generic. Identifiers default to placeholders — the operator overrides
them in a local config file or by constructing EngineConfig directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


DEFAULT_AUDIT_LOG_PATH = "artifacts/OSINT_audit_log.md"


@dataclass
class EngineConfig:
    """Configuration for a TriggerEngine instance.

    self_identifiers
        Strings that mark a query as targeting the operator. Matched
        case-insensitively. Operator fills in real values locally; the
        placeholders below are intentionally non-matching.
    self_context_pairs
        Pairs of (location_hint, role_hint). Both must appear in the same
        query/context blob for it to count as self-targeted. Useful when a
        single token (e.g. a common first name) is too noisy on its own.
    audit_log_path
        Where to append structured audit entries. Created on first write.
    deep_threshold / borderline_threshold
        Stage 2 intent classifier thresholds.
    """

    self_identifiers: list[str] = field(
        default_factory=lambda: [
            "<OPERATOR_NAME_PLACEHOLDER>",
            "<OPERATOR_HANDLE_PLACEHOLDER>",
            "<OPERATOR_BUSINESS_PLACEHOLDER>",
        ]
    )
    self_context_pairs: list[tuple[str, str]] = field(default_factory=list)
    self_addresses: list[str] = field(default_factory=list)
    self_emails: list[str] = field(default_factory=list)
    self_phones: list[str] = field(default_factory=list)
    audit_log_path: str = DEFAULT_AUDIT_LOG_PATH
    deep_threshold: int = 2
    borderline_threshold: int = 1

    def normalized_identifiers(self) -> list[str]:
        """All self-marker strings (identifiers + addresses + emails + phones).

        Used by the firewall to decide whether a query targets the operator.
        Phones are normalized to digits only so "(347) 555-1212" matches
        "3475551212" — search engines drop separators.
        """
        bag: list[str] = []
        for source in (
            self.self_identifiers,
            self.self_addresses,
            self.self_emails,
        ):
            bag.extend(i.lower() for i in source if i)
        for phone in self.self_phones:
            if phone:
                bag.append(phone.lower())
                digits = _digits_only(phone)
                if digits:
                    bag.append(digits)
        return bag

    def normalized_context_pairs(self) -> list[tuple[str, str]]:
        return [(a.lower(), b.lower()) for a, b in self_context_pairs_iter(self.self_context_pairs)]


def _digits_only(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


def self_context_pairs_iter(pairs: Iterable) -> Iterable[tuple[str, str]]:
    for pair in pairs:
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            yield (str(pair[0]), str(pair[1]))


def load_config(path: str | Path) -> EngineConfig:
    """Load an EngineConfig from a JSON file. Missing fields use defaults."""
    raw = json.loads(Path(path).read_text())
    return EngineConfig(
        self_identifiers=raw.get("self_identifiers", []),
        self_context_pairs=[tuple(p) for p in raw.get("self_context_pairs", [])],
        self_addresses=raw.get("self_addresses", []),
        self_emails=raw.get("self_emails", []),
        self_phones=raw.get("self_phones", []),
        audit_log_path=raw.get("audit_log_path", DEFAULT_AUDIT_LOG_PATH),
        deep_threshold=raw.get("deep_threshold", 2),
        borderline_threshold=raw.get("borderline_threshold", 1),
    )
