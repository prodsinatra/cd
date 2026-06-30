from osint_engine.canary import detect_canary_touch


def test_empty_returns_none():
    assert detect_canary_touch("") is None


def test_clean_text_returns_none():
    assert detect_canary_touch("just a normal sentence") is None


def test_catches_canary_term():
    out = detect_canary_touch("the honeytoken was triggered")
    assert out == {"canary_terms": ["honeytoken"]}


def test_catches_osint_tool_name():
    out = detect_canary_touch("ran SpiderFoot against the domain")
    assert out == {"osint_tools": ["spiderfoot"]}


def test_catches_both_categories():
    out = detect_canary_touch("Shodan flagged a canarytoken on the host")
    assert "osint_tools" in out and "canary_terms" in out
    assert "shodan" in out["osint_tools"]
    assert "canarytoken" in out["canary_terms"]


def test_case_insensitive():
    out = detect_canary_touch("MALTEGO scan results")
    assert out == {"osint_tools": ["maltego"]}
