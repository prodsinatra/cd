"""Two-stage privacy firewall.

Stage 1: deterministic keyword check for obviously deep-profiling language.
Stage 2: lightweight intent classifier for ambiguous self-targeted queries.
"""

from __future__ import annotations

from typing import Literal

from osint_engine.config import EngineConfig


Intent = Literal["light_lookup", "borderline", "deep_profiling"]


DEEP_PROFILING_INDICATORS: tuple[str, ...] = (
    "network mapping",
    "social scraping",
    "timeline reconstruction",
    "exhaustive footprint",
    "exhaustive public footprint",
    "connection clustering",
    "full osint profile",
    "dox",
    "doxxing",
    "full background check",
    "deep research on self",
)

DEEP_INTENT_MARKERS: tuple[str, ...] = (
    "full profile",
    "network map",
    "all connections",
    "complete history",
    "social graph",
    "relationship mapping",
    "hidden accounts",
    "private data",
)

LIGHT_INTENT_MARKERS: tuple[str, ...] = (
    "public info",
    "basic search",
    "quick check",
    "public record",
    "general mention",
)


def is_clear_deep_profiling(query: str, context: str) -> bool:
    """Stage 1: substring match against obvious deep-profiling vocabulary.

    `dox` is matched as a whole token to avoid colliding with words like
    `doxology` or `paradox`. The other indicators are multi-word phrases
    that are safe to substring-match.
    """
    combined = f"{query} {context}".lower()
    for indicator in DEEP_PROFILING_INDICATORS:
        if indicator == "dox":
            if _has_whole_word(combined, "dox"):
                return True
            continue
        if indicator in combined:
            return True
    return False


def contains_self_identifiers(query: str, context: str, config: EngineConfig) -> bool:
    """Return True if the query/context mentions the operator.

    Two ways to match:
      1. Any single configured self_identifier substring.
      2. Both halves of any (location, role) pair from self_context_pairs.
    """
    combined = f"{query} {context}".lower()

    for ident in config.normalized_identifiers():
        if ident and ident in combined:
            return True

    for loc, role in config.normalized_context_pairs():
        if loc and role and loc in combined and role in combined:
            return True

    return False


def classify_research_intent(
    query: str,
    context: str,
    previous_results: str,
    config: EngineConfig,
) -> Intent:
    """Stage 2: count deep vs light markers across all available text.

    Returns one of "deep_profiling", "borderline", "light_lookup".
    """
    combined = f"{query} {context} {previous_results}".lower()

    deep_count = sum(1 for m in DEEP_INTENT_MARKERS if m in combined)
    light_count = sum(1 for m in LIGHT_INTENT_MARKERS if m in combined)

    if deep_count >= config.deep_threshold:
        return "deep_profiling"
    if deep_count >= config.borderline_threshold and light_count == 0:
        return "borderline"
    return "light_lookup"


def _has_whole_word(text: str, word: str) -> bool:
    """Whole-word containment for short ambiguous tokens like 'dox'."""
    import re

    return re.search(rf"\b{re.escape(word)}\b", text) is not None
