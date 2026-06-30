from osint_engine.config import EngineConfig
from osint_engine.extractors import (
    NO_PII_MARKER,
    detect_self_pii_leak,
    extract_address_signals,
    extract_email_signals,
    extract_geo_signals,
    extract_mac_signals,
    extract_phone_signals,
    extract_pii_signals,
)


class TestAddress:
    def test_finds_street(self):
        out = extract_address_signals("They live at 123 Main St, Brooklyn.")
        assert "streets" in out
        assert any("Main" in s for s in out["streets"])

    def test_finds_avenue_with_words(self):
        out = extract_address_signals("Office at 1600 Pennsylvania Avenue, DC")
        assert "streets" in out
        assert any("Pennsylvania" in s for s in out["streets"])

    def test_postal_code_needs_context(self):
        # Bare 5-digit number must NOT be flagged as a postal code.
        assert extract_address_signals("Order #11215 shipped") == NO_PII_MARKER

    def test_postal_code_with_context(self):
        out = extract_address_signals("ZIP: 11215")
        assert out["postal_codes"] == ["11215"]

    def test_postcode_uk_format(self):
        out = extract_address_signals("postcode SW1A 1AA")
        assert "postal_codes" in out


class TestEmail:
    def test_finds_email(self):
        out = extract_email_signals("contact me at jdoe@example.com please")
        assert out == {"emails": ["jdoe@example.com"]}

    def test_no_email(self):
        assert extract_email_signals("nothing here") == NO_PII_MARKER

    def test_deduplicates(self):
        out = extract_email_signals("a@x.com and a@x.com again")
        assert out == {"emails": ["a@x.com"]}


class TestPhone:
    def test_finds_paren_format(self):
        out = extract_phone_signals("call (347) 555-1212 tomorrow")
        assert out == {"phones": ["(347) 555-1212"]}

    def test_finds_dash_format(self):
        out = extract_phone_signals("phone 347-555-1212")
        assert out == {"phones": ["347-555-1212"]}

    def test_finds_plus_one(self):
        out = extract_phone_signals("dial +1 347-555-1212 now")
        assert "phones" in out

    def test_rejects_raw_10_digit(self):
        # Bare 10 digits should not match — too noisy.
        assert extract_phone_signals("order id 3475551212") == NO_PII_MARKER


class TestGeo:
    def test_finds_lat_lng(self):
        out = extract_geo_signals("GPS 40.6782, -73.9442")
        assert out == {"coordinates": ["40.6782, -73.9442"]}

    def test_skips_integer_pair(self):
        # 12, 34 is just two numbers with a comma.
        assert extract_geo_signals("range 12.0, 34.0") == NO_PII_MARKER


class TestMac:
    def test_finds_colon_mac(self):
        out = extract_mac_signals("device mac AA:BB:CC:11:22:33")
        assert out == {"mac_addresses": ["AA:BB:CC:11:22:33"]}

    def test_finds_dash_mac(self):
        out = extract_mac_signals("nic aa-bb-cc-11-22-33")
        assert out == {"mac_addresses": ["aa-bb-cc-11-22-33"]}


class TestAggregator:
    def test_empty_returns_marker(self):
        assert extract_pii_signals("") == NO_PII_MARKER

    def test_bundles_multiple_categories(self):
        out = extract_pii_signals(
            "user a@x.com at 123 Main St; call (347) 555-1212; "
            "device AA:BB:CC:11:22:33"
        )
        assert {"address", "email", "phone", "mac"}.issubset(out.keys())


class TestSelfPiiLeak:
    def test_detects_email_leak(self):
        config = EngineConfig(self_emails=["me@example.com"])
        out = detect_self_pii_leak("reached out at me@example.com", config)
        assert out == {"emails": ["me@example.com"]}

    def test_detects_address_leak(self):
        config = EngineConfig(self_addresses=["123 Main St"])
        out = detect_self_pii_leak("delivered to 123 Main St yesterday", config)
        assert out == {"addresses": ["123 Main St"]}

    def test_phone_match_is_digit_normalized(self):
        config = EngineConfig(self_phones=["(347) 555-1212"])
        # Result formats the phone differently.
        out = detect_self_pii_leak("call 3475551212 today", config)
        assert out == {"phones": ["(347) 555-1212"]}

    def test_no_leak_returns_none(self):
        config = EngineConfig(self_emails=["me@example.com"])
        assert detect_self_pii_leak("nothing relevant", config) is None
