"""Main trigger engine.

Coordinates the two-stage firewall, signal extraction, canary detection,
and audit logging. The public entry point is `TriggerEngine.evaluate` (or
the module-level `evaluate_osint_trigger` convenience wrapper).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from osint_engine.audit import append_to_audit_log, current_timestamp
from osint_engine.banner import format_banner
from osint_engine.canary import detect_canary_touch
from osint_engine.config import EngineConfig
from osint_engine.extractors import (
    detect_self_pii_leak,
    extract_fingerprint_signals,
    extract_ip_device_signals,
    extract_pii_signals,
)
from osint_engine.firewall import (
    classify_research_intent,
    contains_self_identifiers,
    is_clear_deep_profiling,
)


Action = str  # "BLOCK" | "ALLOW_WITH_WARNING" | "ALLOW"


@dataclass
class TriggerDecision:
    """Structured result of a trigger evaluation."""

    action: Action
    alert_level: str
    intent_classification: str
    reason: str
    ip_device_info: Any
    fingerprint_signals: Any
    canary_hits: Any = None
    pii_signals: Any = None
    self_pii_leak: Any = None
    should_block_research: bool = False
    message: str = ""
    banner: str = ""
    timestamp: str = ""
    audit_outcome: str = ""
    extras: dict = field(default_factory=dict)


class TriggerEngine:
    def __init__(self, config: EngineConfig | None = None) -> None:
        self.config = config or EngineConfig()

    def evaluate(
        self,
        query: str,
        context: str = "",
        tool_name: str = "unknown",
        previous_results: str = "",
    ) -> TriggerDecision:
        timestamp = current_timestamp()

        ip_signals = extract_ip_device_signals(previous_results)
        fp_signals = extract_fingerprint_signals(previous_results)
        canary_hits = detect_canary_touch(f"{query} {context} {previous_results}")
        pii_signals = extract_pii_signals(previous_results)
        self_pii_leak = detect_self_pii_leak(previous_results, self.config)

        signal_kwargs = dict(
            ip_signals=ip_signals,
            fp_signals=fp_signals,
            canary_hits=canary_hits,
            pii_signals=pii_signals,
            self_pii_leak=self_pii_leak,
        )

        # Stage 1: fast deterministic check.
        if is_clear_deep_profiling(query, context):
            decision = self._blocked(
                timestamp=timestamp,
                level="Level 2",
                reason="Clear deep profiling indicators detected (Stage 1)",
                intent="deep_profiling",
                tool=tool_name,
                query=query,
                audit_outcome="BLOCKED - Stage 1 deep profiling",
                **signal_kwargs,
            )
            self._write_audit(decision, tool_name, query)
            return decision

        is_self = contains_self_identifiers(query, context, self.config)

        if is_self:
            intent = classify_research_intent(
                query, context, previous_results, self.config
            )

            if intent == "deep_profiling":
                decision = self._blocked(
                    timestamp=timestamp,
                    level="Level 2",
                    reason="Intent classifier returned deep_profiling (Stage 2)",
                    intent="deep_profiling",
                    tool=tool_name,
                    query=query,
                    audit_outcome="BLOCKED - Stage 2 intent",
                    **signal_kwargs,
                )
                self._write_audit(decision, tool_name, query)
                return decision

            if intent == "borderline":
                decision = self._allow_with_warning(
                    timestamp=timestamp,
                    tool=tool_name,
                    query=query,
                    **signal_kwargs,
                )
                self._write_audit(decision, tool_name, query)
                return decision

            # Light self-targeted lookup: allow, log as Level 1.
            decision = self._allow_self_light(
                timestamp=timestamp,
                tool=tool_name,
                query=query,
                **signal_kwargs,
            )
            self._write_audit(decision, tool_name, query)
            return decision

        # Non-self query path. Self-PII leak in results is high-signal even
        # when the query itself looked benign.
        decision = self._allow_non_self(
            timestamp=timestamp,
            tool=tool_name,
            query=query,
            **signal_kwargs,
        )
        if canary_hits or self_pii_leak:
            self._write_audit(decision, tool_name, query)
        return decision

    # ---- Decision builders -------------------------------------------------

    def _blocked(
        self,
        *,
        timestamp: str,
        level: str,
        reason: str,
        intent: str,
        ip_signals: Any,
        fp_signals: Any,
        canary_hits: Any,
        pii_signals: Any,
        self_pii_leak: Any,
        tool: str,
        query: str,
        audit_outcome: str,
    ) -> TriggerDecision:
        banner = format_banner(
            level=level,
            tool=tool,
            query=query,
            reason=reason,
            intent=intent,
            action="BLOCKED",
            ip_signals=ip_signals,
            fingerprint_signals=fp_signals,
            canary_hits=canary_hits,
            pii_signals=pii_signals,
            self_pii_leak=self_pii_leak,
            audit_ref=self.config.audit_log_path,
        )
        return TriggerDecision(
            action="BLOCK",
            alert_level=level,
            intent_classification=intent,
            reason=reason,
            ip_device_info=ip_signals,
            fingerprint_signals=fp_signals,
            canary_hits=canary_hits,
            pii_signals=pii_signals,
            self_pii_leak=self_pii_leak,
            should_block_research=True,
            message="Research blocked per privacy firewall. See audit log for details.",
            banner=banner,
            timestamp=timestamp,
            audit_outcome=audit_outcome,
        )

    def _allow_with_warning(
        self,
        *,
        timestamp: str,
        ip_signals: Any,
        fp_signals: Any,
        canary_hits: Any,
        pii_signals: Any,
        self_pii_leak: Any,
        tool: str,
        query: str,
    ) -> TriggerDecision:
        reason = "Borderline self-targeted query (Stage 2)"
        banner = format_banner(
            level="Level 1 - Borderline",
            tool=tool,
            query=query,
            reason=reason,
            intent="borderline",
            action="ALLOWED WITH WARNING",
            ip_signals=ip_signals,
            fingerprint_signals=fp_signals,
            canary_hits=canary_hits,
            pii_signals=pii_signals,
            self_pii_leak=self_pii_leak,
            audit_ref=self.config.audit_log_path,
        )
        return TriggerDecision(
            action="ALLOW_WITH_WARNING",
            alert_level="Level 1 - Borderline",
            intent_classification="borderline",
            reason=reason,
            ip_device_info=ip_signals,
            fingerprint_signals=fp_signals,
            canary_hits=canary_hits,
            pii_signals=pii_signals,
            self_pii_leak=self_pii_leak,
            should_block_research=False,
            message="Borderline self-targeted query. Logged for review.",
            banner=banner,
            timestamp=timestamp,
            audit_outcome="BORDERLINE - Stage 2",
        )

    def _allow_self_light(
        self,
        *,
        timestamp: str,
        ip_signals: Any,
        fp_signals: Any,
        canary_hits: Any,
        pii_signals: Any,
        self_pii_leak: Any,
        tool: str,
        query: str,
    ) -> TriggerDecision:
        reason = "Light self-targeted lookup"
        banner = format_banner(
            level="Level 1",
            tool=tool,
            query=query,
            reason=reason,
            intent="light_lookup",
            action="ALLOWED",
            ip_signals=ip_signals,
            fingerprint_signals=fp_signals,
            canary_hits=canary_hits,
            pii_signals=pii_signals,
            self_pii_leak=self_pii_leak,
            audit_ref=self.config.audit_log_path,
        )
        return TriggerDecision(
            action="ALLOW",
            alert_level="Level 1",
            intent_classification="light_lookup",
            reason=reason,
            ip_device_info=ip_signals,
            fingerprint_signals=fp_signals,
            canary_hits=canary_hits,
            pii_signals=pii_signals,
            self_pii_leak=self_pii_leak,
            should_block_research=False,
            message="Light self-targeted lookup logged.",
            banner=banner,
            timestamp=timestamp,
            audit_outcome="LIGHT SELF-TARGETED - ALLOWED",
        )

    def _allow_non_self(
        self,
        *,
        timestamp: str,
        ip_signals: Any,
        fp_signals: Any,
        canary_hits: Any,
        pii_signals: Any,
        self_pii_leak: Any,
        tool: str,
        query: str,
    ) -> TriggerDecision:
        # Pick the strongest reason for the alert (self-PII leak beats
        # canary beats silent). Operator's own PII appearing in scraped
        # results is the loudest signal here.
        if self_pii_leak:
            level = "Level 1 - Self PII Leak"
            reason = "Operator PII appeared in scraped results"
            outcome = "SELF PII LEAK - NON-SELF QUERY"
        elif canary_hits:
            level = "Level 1 - Canary"
            reason = "Canary token or OSINT tool reference detected"
            outcome = "CANARY HIT - NON-SELF"
        else:
            level = "None"
            reason = "Non-self query"
            outcome = "ALLOWED"

        banner = ""
        if self_pii_leak or canary_hits:
            banner = format_banner(
                level=level,
                tool=tool,
                query=query,
                reason=reason,
                intent="light_lookup",
                action="ALLOWED",
                ip_signals=ip_signals,
                fingerprint_signals=fp_signals,
                canary_hits=canary_hits,
                pii_signals=pii_signals,
                self_pii_leak=self_pii_leak,
                audit_ref=self.config.audit_log_path,
            )
        return TriggerDecision(
            action="ALLOW",
            alert_level=level,
            intent_classification="light_lookup",
            reason=reason,
            ip_device_info=ip_signals,
            fingerprint_signals=fp_signals,
            canary_hits=canary_hits,
            pii_signals=pii_signals,
            self_pii_leak=self_pii_leak,
            should_block_research=False,
            message="",
            banner=banner,
            timestamp=timestamp,
            audit_outcome=outcome,
        )

    def _write_audit(self, decision: TriggerDecision, tool: str, query: str) -> None:
        append_to_audit_log(
            self.config.audit_log_path,
            timestamp=decision.timestamp,
            tool=tool,
            query=query,
            outcome=decision.audit_outcome,
            response=decision,
        )


def evaluate_osint_trigger(
    query: str,
    context: str = "",
    tool_name: str = "unknown",
    previous_results: str = "",
    config: EngineConfig | None = None,
) -> TriggerDecision:
    """Module-level convenience wrapper around TriggerEngine.evaluate."""
    return TriggerEngine(config).evaluate(query, context, tool_name, previous_results)
