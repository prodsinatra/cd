"""Protective OSINT workflow.

Drives controlled self-research through the trigger engine. Every result
is passed through `TriggerEngine.evaluate` so the operator gets a complete
record of what was discovered and what signals leaked.

The actual web/API calls are pluggable: pass any callable matching the
LookupFn signature. Each lookup result is tagged PROTECTIVE_OSINT in the
audit log.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

from osint_engine.engine import TriggerDecision, TriggerEngine


LookupFn = Callable[[str], str]


@dataclass
class ScopedLookup:
    """One safe lookup scope to run during protective sweeps."""

    label: str
    query: str


@dataclass
class SelfExposureReport:
    findings: list[dict] = field(default_factory=list)
    fingerprint_signals: list[dict] = field(default_factory=list)
    ip_signals: list[dict] = field(default_factory=list)
    canary_hits: list[dict] = field(default_factory=list)
    pii_signals: list[dict] = field(default_factory=list)
    self_pii_leaks: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def add_finding(self, label: str, decision: TriggerDecision, raw: str) -> None:
        self.findings.append(
            {
                "label": label,
                "action": decision.action,
                "alert_level": decision.alert_level,
                "raw_excerpt": raw[:500],
            }
        )
        if decision.fingerprint_signals and not isinstance(
            decision.fingerprint_signals, str
        ):
            self.fingerprint_signals.append({label: decision.fingerprint_signals})
        if decision.ip_device_info and not isinstance(decision.ip_device_info, str):
            self.ip_signals.append({label: decision.ip_device_info})
        if decision.canary_hits:
            self.canary_hits.append({label: decision.canary_hits})
        if decision.pii_signals and not isinstance(decision.pii_signals, str):
            self.pii_signals.append({label: decision.pii_signals})
        if decision.self_pii_leak:
            self.self_pii_leaks.append({label: decision.self_pii_leak})


def run_protective_osint(
    scopes: Sequence[ScopedLookup],
    lookup_fn: LookupFn,
    engine: TriggerEngine,
) -> SelfExposureReport:
    """Run a constrained self-research sweep.

    Each scope's query is passed to `lookup_fn`. The returned text is fed
    back through `engine.evaluate` as `previous_results` so any leaked
    fingerprint/IP/canary signals get extracted and audited under the
    PROTECTIVE_OSINT tag.
    """
    report = SelfExposureReport()

    for scope in scopes:
        raw_result = lookup_fn(scope.query)
        decision = engine.evaluate(
            query=scope.query,
            context=f"PROTECTIVE_OSINT scope={scope.label}",
            tool_name=f"protective:{scope.label}",
            previous_results=raw_result,
        )
        report.add_finding(scope.label, decision, raw_result)

    report.recommendations = _derive_recommendations(report)
    return report


def _derive_recommendations(report: SelfExposureReport) -> list[str]:
    recs: list[str] = []
    if report.self_pii_leaks:
        recs.append(
            "Configured operator PII (address/email/phone) appeared in "
            "scraped results — request removal from the source, file data "
            "broker opt-outs, and rotate the affected contact channel if "
            "feasible."
        )
    if report.pii_signals:
        recs.append(
            "Third-party PII (addresses, emails, phones, geo coords, MAC "
            "addresses) was found in scraped results — narrow the scope so "
            "you are not inadvertently collecting other people's PII."
        )
    if report.fingerprint_signals:
        recs.append(
            "Browser/device fingerprint signals appeared in scraped results — "
            "audit which sites are leaking client metadata and consider a "
            "fingerprint-resistant browser profile."
        )
    if report.ip_signals:
        recs.append(
            "IP addresses appeared in scraped results — check log retention "
            "and CDN/edge config to make sure raw client IPs are not exposed."
        )
    if report.canary_hits:
        recs.append(
            "Canary token / OSINT-tool references hit — investigate the "
            "originating source; this is a strong signal of active probing."
        )
    blocked = [f for f in report.findings if f["action"] == "BLOCK"]
    if blocked:
        recs.append(
            f"{len(blocked)} scope(s) were blocked by the firewall. Review "
            "the scope queries — they may have drifted into deep-profiling."
        )
    if not recs:
        recs.append("No high-signal exposure detected in this sweep.")
    return recs
