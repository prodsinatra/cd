from osint_engine.extractors import (
    NO_FP_MARKER,
    NO_IP_MARKER,
    extract_fingerprint_signals,
    extract_ip_device_signals,
)


class TestIPExtraction:
    def test_empty_input(self):
        assert extract_ip_device_signals("") == NO_IP_MARKER

    def test_finds_ipv4(self):
        out = extract_ip_device_signals("connection from 192.168.1.10 logged")
        assert out == {"ipv4": ["192.168.1.10"]}

    def test_finds_multiple_ipv4(self):
        out = extract_ip_device_signals("hosts: 10.0.0.1, 10.0.0.2 and 10.0.0.1 again")
        assert out == {"ipv4": ["10.0.0.1", "10.0.0.2"]}

    def test_rejects_invalid_ipv4_octets(self):
        # 999.999.999.999 matches the regex shape but fails octet validation.
        assert extract_ip_device_signals("999.999.999.999") == NO_IP_MARKER

    def test_finds_ipv6(self):
        out = extract_ip_device_signals(
            "client 2001:0db8:85a3:0000:0000:8a2e:0370:7334 connected"
        )
        assert "ipv6" in out
        assert out["ipv6"] == ["2001:0db8:85a3:0000:0000:8a2e:0370:7334"]

    def test_no_match_returns_marker(self):
        assert extract_ip_device_signals("nothing here") == NO_IP_MARKER


class TestFingerprintExtraction:
    def test_empty_input(self):
        assert extract_fingerprint_signals("") == NO_FP_MARKER

    def test_finds_canvas(self):
        out = extract_fingerprint_signals(
            "their canvas fingerprint was extracted via getImageData"
        )
        assert "canvas_webgl" in out
        assert "canvas" in out["canvas_webgl"]

    def test_finds_audio(self):
        out = extract_fingerprint_signals(
            "AudioContext fingerprint matched profile hash"
        )
        assert "audio_fingerprint" in out

    def test_finds_ja3(self):
        out = extract_fingerprint_signals("TLS handshake JA3 hash: abc123")
        assert "tls_ja3" in out

    def test_no_signals_returns_marker(self):
        assert extract_fingerprint_signals("plain text result") == NO_FP_MARKER

    def test_finds_multiple_categories(self):
        out = extract_fingerprint_signals(
            "User-Agent: Mozilla, canvas fingerprint stored, JA3=abc"
        )
        assert {"canvas_webgl", "user_agent", "tls_ja3"}.issubset(out.keys())
