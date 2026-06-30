import json
from pathlib import Path

import pytest

from osint_engine.config import EngineConfig
from osint_engine.engine import TriggerEngine, evaluate_osint_trigger


@pytest.fixture
def config(tmp_path):
    return EngineConfig(
        self_identifiers=["jdoe-music", "808szn"],
        self_context_pairs=[("brooklyn", "music producer")],
        audit_log_path=str(tmp_path / "audit.md"),
    )


@pytest.fixture
def engine(config):
    return TriggerEngine(config)


def _read_audit(config: EngineConfig) -> str:
    path = Path(config.audit_log_path)
    return path.read_text() if path.exists() else ""


class TestStage1Block:
    def test_dox_blocks_and_audits(self, engine, config):
        decision = engine.evaluate(
            query="dox this 808szn person",
            tool_name="search",
        )
        assert decision.action == "BLOCK"
        assert decision.should_block_research is True
        assert decision.alert_level == "Level 2"
        assert "Stage 1" in decision.reason
        assert "OSINT SELF-ALERT" in decision.banner
        assert "BLOCKED - Stage 1" in _read_audit(config)


class TestStage2Block:
    def test_self_plus_deep_intent_blocks(self, engine, config):
        decision = engine.evaluate(
            query="full profile and social graph for 808szn",
            tool_name="search",
        )
        assert decision.action == "BLOCK"
        assert "Stage 2" in decision.reason
        assert "BLOCKED - Stage 2" in _read_audit(config)


class TestStage2Borderline:
    def test_self_plus_one_deep_marker_warns(self, engine, config):
        decision = engine.evaluate(
            query="hidden accounts linked to 808szn",
            tool_name="search",
        )
        assert decision.action == "ALLOW_WITH_WARNING"
        assert decision.alert_level == "Level 1 - Borderline"
        assert decision.should_block_research is False
        assert "OSINT SELF-ALERT" in decision.banner


class TestLightSelfTargeted:
    def test_light_self_lookup_allowed_and_logged(self, engine, config):
        decision = engine.evaluate(
            query="recent press mentions of 808szn",
            tool_name="search",
        )
        assert decision.action == "ALLOW"
        assert decision.alert_level == "Level 1"
        assert "LIGHT SELF-TARGETED" in _read_audit(config)


class TestNonSelf:
    def test_clean_query_is_silent(self, engine, config):
        decision = engine.evaluate(query="best beat-making tutorials")
        assert decision.action == "ALLOW"
        assert decision.banner == ""
        assert not Path(config.audit_log_path).exists()


class TestCanaryDuringNonSelf:
    def test_canary_hit_on_non_self_still_audits(self, engine, config):
        decision = engine.evaluate(
            query="any new tools",
            previous_results="SpiderFoot scan returned matches",
        )
        assert decision.action == "ALLOW"
        assert decision.canary_hits is not None
        assert decision.banner  # banner fires even though it's non-self
        assert "CANARY HIT - NON-SELF" in _read_audit(config)


class TestSignalCapture:
    def test_ip_and_fingerprint_get_attached(self, engine):
        decision = engine.evaluate(
            query="press mentions of 808szn",
            previous_results=(
                "Visitor 203.0.113.7 was profiled with canvas fingerprint xyz"
            ),
        )
        assert decision.ip_device_info == {"ipv4": ["203.0.113.7"]}
        assert "canvas_webgl" in decision.fingerprint_signals


class TestAuditEntryShape:
    def test_audit_entry_is_valid_json(self, engine, config):
        engine.evaluate(query="dox 808szn")
        text = _read_audit(config)
        assert "```json" in text
        block = text.split("```json", 1)[1].split("```", 1)[0]
        parsed = json.loads(block)
        assert parsed["outcome"].startswith("BLOCKED")
        assert "response" in parsed


class TestModuleWrapper:
    def test_module_level_wrapper_works(self, config):
        decision = evaluate_osint_trigger(
            query="dox 808szn",
            config=config,
        )
        assert decision.action == "BLOCK"
