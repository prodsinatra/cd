"""Engine-level tests for the PII / self-PII-leak layer."""

from pathlib import Path

import pytest

from osint_engine.config import EngineConfig
from osint_engine.engine import TriggerEngine


@pytest.fixture
def config(tmp_path):
    return EngineConfig(
        self_identifiers=["808szn"],
        self_addresses=["123 Main St"],
        self_emails=["me@example.com"],
        self_phones=["(347) 555-1212"],
        audit_log_path=str(tmp_path / "audit.md"),
    )


@pytest.fixture
def engine(config):
    return TriggerEngine(config)


def _read_audit(config: EngineConfig) -> str:
    path = Path(config.audit_log_path)
    return path.read_text() if path.exists() else ""


class TestSelfPiiLeakOnNonSelfQuery:
    def test_promotes_to_pii_leak_level(self, engine, config):
        decision = engine.evaluate(
            query="best music studios in brooklyn",  # non-self query
            previous_results="contact info: me@example.com",
        )
        assert decision.alert_level == "Level 1 - Self PII Leak"
        assert decision.self_pii_leak == {"emails": ["me@example.com"]}
        assert "Operator PII leak detected" in decision.banner
        assert "SELF PII LEAK" in _read_audit(config)

    def test_phone_leak_normalized(self, engine, config):
        decision = engine.evaluate(
            query="industry phone book",
            previous_results="we have 3475551212 on file",
        )
        assert decision.alert_level == "Level 1 - Self PII Leak"
        assert decision.self_pii_leak == {"phones": ["(347) 555-1212"]}

    def test_clean_results_stay_silent(self, engine, config):
        decision = engine.evaluate(
            query="general beat-making tips",
            previous_results="here are some tips...",
        )
        assert decision.alert_level == "None"
        assert decision.banner == ""


class TestSelfPiiLeakWinsOverCanary:
    def test_self_pii_outranks_canary(self, engine, config):
        decision = engine.evaluate(
            query="random query",
            previous_results=(
                "SpiderFoot scan found contact: me@example.com"
            ),
        )
        # Self-PII leak is the loudest signal, so it owns the level.
        assert decision.alert_level == "Level 1 - Self PII Leak"
        # But canary hits are still recorded in the decision.
        assert decision.canary_hits is not None


class TestStreetAddressInIdentifiers:
    def test_query_with_self_street_blocks_via_self_match(self, engine, config):
        # An address listed in self_addresses also makes the query
        # self-targeted, so deep-profiling intent on top of it blocks.
        decision = engine.evaluate(
            query="full profile of resident at 123 Main St with social graph"
        )
        assert decision.action == "BLOCK"


class TestPiiSignalsFieldPopulated:
    def test_pii_signals_dict_attached(self, engine):
        decision = engine.evaluate(
            query="public mentions of 808szn",
            previous_results="email a@x.com, addr 1 Park Ave, mac AA:BB:CC:11:22:33",
        )
        assert isinstance(decision.pii_signals, dict)
        assert {"address", "email", "mac"}.issubset(decision.pii_signals.keys())
