#!/usr/bin/env python3
"""Tests for the WAV uniquifier.

Run with: python test_uniquify.py
Generates tones in memory, perturbs them, and checks that the output is
unique (different bytes) yet stays within an inaudible distance of the
original for every supported sample width.
"""

import hashlib
import math
import os
import random
import struct
import tempfile
import wave

from uniquify import uniquify_samples, uniquify_file


def _sine_frames(sample_width: int, n: int = 4000, freq: float = 440.0,
                 rate: int = 44100) -> bytes:
    """Generate one channel of PCM sine samples at the given sample width."""
    out = bytearray()
    for i in range(n):
        t = math.sin(2 * math.pi * freq * i / rate)
        if sample_width == 1:
            out.append(max(0, min(255, int(round(t * 100)) + 128)))
        else:
            peak = (1 << (sample_width * 8 - 1)) - 1
            value = int(round(t * peak * 0.8))
            out += value.to_bytes(sample_width, "little", signed=True)
    return bytes(out)


def _samples(frames: bytes, width: int) -> list[int]:
    if width == 1:
        return list(frames)
    return [
        int.from_bytes(frames[i:i + width], "little", signed=True)
        for i in range(0, len(frames), width)
    ]


def test_output_differs_from_input():
    for width in (1, 2, 3, 4):
        frames = _sine_frames(width)
        out = uniquify_samples(frames, width, random.Random(7), depth=1)
        assert len(out) == len(frames)
        assert out != frames, f"width {width}: output identical to input"
    print("ok: output bytes differ from the input for every width")


def test_perturbation_is_within_depth():
    # depth=1 must never move a sample by more than 1; depth=2 by no more than 3.
    for depth, bound in ((1, 1), (2, 3)):
        for width in (1, 2, 3, 4):
            frames = _sine_frames(width)
            out = uniquify_samples(frames, width, random.Random(99), depth)
            for a, b in zip(_samples(frames, width), _samples(out, width)):
                assert abs(a - b) <= bound, (
                    f"width {width} depth {depth}: moved {a}->{b}"
                )
    print("ok: every sample stays within the requested bit depth")


def test_seed_is_reproducible():
    frames = _sine_frames(2)
    a = uniquify_samples(frames, 2, random.Random(42), depth=1)
    b = uniquify_samples(frames, 2, random.Random(42), depth=1)
    assert a == b, "same seed should give identical output"
    c = uniquify_samples(frames, 2, random.Random(43), depth=1)
    assert c != a, "different seed should (almost surely) differ"
    print("ok: seed makes output reproducible; different seeds diverge")


def test_two_random_runs_are_unique():
    # No seed -> os.urandom; two files of the same source must not collide.
    frames = _sine_frames(2)
    digests = set()
    for _ in range(5):
        rng = random.Random(os.urandom(16))
        out = uniquify_samples(frames, 2, rng, depth=1)
        digests.add(hashlib.sha256(out).hexdigest())
    assert len(digests) == 5, "random runs collided"
    print("ok: independent runs each produce a unique file hash")


def test_clamping_at_extremes():
    # Max and min 16-bit samples must not overflow when nudged.
    frames = struct.pack("<hh", 32767, -32768)
    out = uniquify_samples(frames, 2, random.Random(1), depth=4)
    hi, lo = struct.unpack("<hh", out)
    assert -32768 <= lo <= 32767 and -32768 <= hi <= 32767
    print("ok: samples at the format extremes stay in range")


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

        uniquify_file(src, dst, seed=5)

        with wave.open(dst, "rb") as r:
            assert r.getnchannels() == 1
            assert r.getsampwidth() == 2
            assert r.getframerate() == 44100
            out_frames = r.readframes(r.getnframes())

        assert out_frames != frames, "file should be perturbed"
        assert len(out_frames) == len(frames)
    print("ok: WAV file round-trip preserves params and stays same length")


if __name__ == "__main__":
    test_output_differs_from_input()
    test_perturbation_is_within_depth()
    test_seed_is_reproducible()
    test_two_random_runs_are_unique()
    test_clamping_at_extremes()
    test_roundtrip_through_wav_file()
    print("\nall tests passed")
