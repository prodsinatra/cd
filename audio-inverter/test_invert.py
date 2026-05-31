#!/usr/bin/env python3
"""Self-contained tests for the WAV phase inverter.

Run with: python test_invert.py
No external dependencies — just generates tones in memory, inverts them, and
checks the math holds for every supported sample width.
"""

import math
import os
import struct
import tempfile
import wave

from invert import invert_samples, invert_file


def _sine_frames(sample_width: int, n: int = 2000, freq: float = 440.0,
                 rate: int = 44100) -> bytes:
    """Generate one channel of PCM sine samples at the given sample width."""
    out = bytearray()
    for i in range(n):
        t = math.sin(2 * math.pi * freq * i / rate)
        if sample_width == 1:
            # unsigned 8-bit centred on 128
            out.append(max(0, min(255, int(round(t * 100)) + 128)))
        else:
            peak = (1 << (sample_width * 8 - 1)) - 1
            value = int(round(t * peak * 0.8))
            out += value.to_bytes(sample_width, "little", signed=True)
    return bytes(out)


def test_signed_widths_cancel():
    for width in (2, 3, 4):
        frames = _sine_frames(width)
        inverted = invert_samples(frames, width)
        assert len(inverted) == len(frames)
        for i in range(0, len(frames), width):
            a = int.from_bytes(frames[i:i + width], "little", signed=True)
            b = int.from_bytes(inverted[i:i + width], "little", signed=True)
            assert a + b == 0, f"width {width}: {a} + {b} != 0"
    print("ok: signed 16/24/32-bit samples cancel to zero")


def test_eight_bit_mirrors():
    frames = _sine_frames(1)
    inverted = invert_samples(frames, 1)
    assert len(inverted) == len(frames)
    for orig, inv in zip(frames, inverted):
        assert orig + inv == 255
    print("ok: 8-bit samples mirror around the midpoint")


def test_most_negative_is_clamped():
    # -32768 has no positive counterpart in 16-bit; it must clamp to +32767.
    frames = struct.pack("<h", -32768)
    inverted = invert_samples(frames, 2)
    assert struct.unpack("<h", inverted)[0] == 32767
    print("ok: most-negative sample is clamped instead of overflowing")


def test_double_inversion_is_identity():
    # Inverting twice should restore the original signed samples exactly.
    for width in (2, 3, 4):
        frames = _sine_frames(width)
        assert invert_samples(invert_samples(frames, width), width) == frames
    print("ok: inverting twice restores the original (signed widths)")


def test_roundtrip_through_wav_file():
    frames = _sine_frames(2)
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in.wav")
        dst = os.path.join(tmp, "out.wav")
        with wave.open(src, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(44100)
            w.writeframes(frames)

        invert_file(src, dst)

        with wave.open(dst, "rb") as r:
            assert r.getnchannels() == 1
            assert r.getsampwidth() == 2
            assert r.getframerate() == 44100
            out_frames = r.readframes(r.getnframes())

        assert out_frames == invert_samples(frames, 2)
    print("ok: WAV file round-trip preserves params and inverts data")


if __name__ == "__main__":
    test_signed_widths_cancel()
    test_eight_bit_mirrors()
    test_most_negative_is_clamped()
    test_double_inversion_is_identity()
    test_roundtrip_through_wav_file()
    print("\nall tests passed")
