from osint_engine.config import EngineConfig
from osint_engine.engine import TriggerEngine
from osint_engine.protective import ScopedLookup, run_protective_osint


def test_run_collects_findings_and_recommendations(tmp_path):
    config = EngineConfig(
        self_identifiers=["808szn"],
        audit_log_path=str(tmp_path / "audit.md"),
    )
    engine = TriggerEngine(config)

    fake_responses = {
        "soundcloud": "public profile for 808szn, 12 tracks",
        "domain": "WHOIS leaked 198.51.100.42 in registrar response",
        "canary": "SpiderFoot scanned the decoy document",
    }

    def lookup(query: str) -> str:
        for key, val in fake_responses.items():
            if key in query:
                return val
        return ""

    scopes = [
        ScopedLookup("soundcloud", "public soundcloud mentions of 808szn"),
        ScopedLookup("domain", "public domain registry mentions of 808szn"),
        ScopedLookup("canary", "any canary mentions of 808szn"),
    ]

    report = run_protective_osint(scopes, lookup, engine)

    labels = [f["label"] for f in report.findings]
    assert labels == ["soundcloud", "domain", "canary"]

    # IP leak from the domain scope should land in ip_signals.
    assert any("domain" in entry for entry in report.ip_signals)
    # Canary hit from the canary scope should land in canary_hits.
    assert any("canary" in entry for entry in report.canary_hits)
    # At minimum we expect IP + canary recommendations.
    rec_text = " ".join(report.recommendations)
    assert "IP addresses" in rec_text
    assert "Canary" in rec_text


def test_empty_sweep_recommends_clean(tmp_path):
    config = EngineConfig(
        self_identifiers=["808szn"],
        audit_log_path=str(tmp_path / "audit.md"),
    )
    engine = TriggerEngine(config)

    scopes = [ScopedLookup("trivial", "public mention of 808szn")]
    report = run_protective_osint(scopes, lambda q: "nothing notable", engine)

    assert report.recommendations == [
        "No high-signal exposure detected in this sweep."
    ]
