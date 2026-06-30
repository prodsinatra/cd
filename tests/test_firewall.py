import pytest

from osint_engine.config import EngineConfig
from osint_engine.firewall import (
    classify_research_intent,
    contains_self_identifiers,
    is_clear_deep_profiling,
)


@pytest.fixture
def config():
    return EngineConfig(
        self_identifiers=["jdoe-music", "808szn"],
        self_context_pairs=[("brooklyn", "music producer")],
    )


class TestStage1:
    def test_catches_doxxing(self):
        assert is_clear_deep_profiling("can you dox this person", "")
        assert is_clear_deep_profiling("planning a doxxing campaign", "")

    def test_dox_does_not_match_paradox(self):
        assert not is_clear_deep_profiling("the paradox of choice", "")

    def test_multi_word_indicators(self):
        assert is_clear_deep_profiling("do network mapping on them", "")
        assert is_clear_deep_profiling("", "exhaustive footprint analysis")
        assert is_clear_deep_profiling("full OSINT profile please", "")

    def test_clean_query_passes(self):
        assert not is_clear_deep_profiling("what's the weather today", "")


class TestSelfIdentifiers:
    def test_single_identifier_match(self, config):
        assert contains_self_identifiers("looking up 808szn", "", config)

    def test_case_insensitive(self, config):
        assert contains_self_identifiers("JDOE-MUSIC profile", "", config)

    def test_context_pair_match(self, config):
        assert contains_self_identifiers(
            "any brooklyn music producer working on beats", "", config
        )

    def test_context_pair_needs_both(self, config):
        assert not contains_self_identifiers("brooklyn pizza review", "", config)
        assert not contains_self_identifiers("music producer in seattle", "", config)

    def test_no_match_when_clean(self, config):
        assert not contains_self_identifiers("python type hints", "", config)


class TestIntentClassifier:
    def test_deep_when_two_markers(self, config):
        intent = classify_research_intent(
            "build a full profile with social graph", "", "", config
        )
        assert intent == "deep_profiling"

    def test_borderline_when_one_deep_no_light(self, config):
        intent = classify_research_intent("any hidden accounts", "", "", config)
        assert intent == "borderline"

    def test_light_when_no_markers(self, config):
        assert classify_research_intent("hello world", "", "", config) == "light_lookup"

    def test_light_when_explicit_light_marker(self, config):
        # one deep marker + one light marker → light_lookup (not borderline)
        intent = classify_research_intent(
            "hidden accounts public record", "", "", config
        )
        assert intent == "light_lookup"

    def test_scans_previous_results_too(self, config):
        intent = classify_research_intent(
            "hi", "", "found full profile with relationship mapping", config
        )
        assert intent == "deep_profiling"
