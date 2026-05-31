#!/usr/bin/env python3
"""Tests for the multi-format audio uniquifier.

Run with: python test_uniquify_audio.py

Requires soundfile + numpy. If they are unavailable the suite skips with a
clear message rather than failing, so the stdlib-only tests can still run in
minimal environments.
"""

import hashlib
import math
import os
import sys
import tempfile

try:
    import numpy as np
    import soundfile as sf
except ImportError as exc:
    print(f"SKIP: soundfile/numpy not installed ({exc})")
    sys.exit(0)

from uniquify_audio import (
    perturb,
    uniquify_audio_file,
    default_output_path,
    PRESETS,
)


def _tone(seconds=0.25, rate=22050, freq=440.0):
    t = np.arange(int(seconds * rate)) / rate
    return (0.6 * np.sin(2 * math.pi * freq * t)).astype(np.float64), rate


def _write(path, data, rate, fmt=None, subtype=None):
    sf.write(path, data, rate, format=fmt, subtype=subtype)


def test_perturb_changes_but_stays_close():
    data, rate = _tone()
    rng = np.random.default_rng(0)
    out = perturb(data, rate, rng, PRESETS["light"], "PCM_16")
    # Light preset adds no pad, so lengths match and the shift is tiny.
    assert out.shape == data.shape
    assert not np.array_equal(out, data)
    # Inaudible: light preset stays within a few quantisation steps.
    step = 1.0 / (1 << 15)
    assert np.max(np.abs(out - data)) < 5 * step
    print("ok: light perturbation changes data but stays near-inaudible")


def test_strong_adds_leading_pad():
    data, rate = _tone()
    rng = np.random.default_rng(1)
    out = perturb(data, rate, rng, PRESETS["strong"], "PCM_16")
    assert out.shape[0] > data.shape[0], "strong preset should prepend frames"
    print("ok: strong preset shifts time alignment with a leading pad")


def test_seed_reproducible_and_diverges():
    data, rate = _tone()
    a = perturb(data, rate, np.random.default_rng(42), PRESETS["strong"], "PCM_16")
    b = perturb(data, rate, np.random.default_rng(42), PRESETS["strong"], "PCM_16")
    assert np.array_equal(a, b), "same seed should reproduce identical output"
    c = perturb(data, rate, np.random.default_rng(43), PRESETS["strong"], "PCM_16")
    assert not (a.shape == c.shape and np.array_equal(a, c))
    print("ok: seed reproducible; different seeds diverge")


def test_roundtrip_unique_hash_per_format():
    data, rate = _tone()
    # Test the lossless / lossy formats this build is most likely to support.
    candidates = {
        "WAV": ".wav",
        "FLAC": ".flac",
        "OGG": ".ogg",
        "AIFF": ".aiff",
    }
    available = sf.available_formats()
    tested = []
    with tempfile.TemporaryDirectory() as tmp:
        for fmt, ext in candidates.items():
            if fmt not in available:
                continue
            src = os.path.join(tmp, f"in{ext}")
            try:
                _write(src, data, rate, fmt=fmt)
            except Exception:
                continue  # subtype not writable in this build; skip
            hashes = set()
            for i in range(3):
                dst = os.path.join(tmp, f"out{i}{ext}")
                uniquify_audio_file(src, dst, seed=None, strength="strong")
                with open(dst, "rb") as fh:
                    hashes.add(hashlib.sha256(fh.read()).hexdigest())
            assert len(hashes) == 3, f"{fmt}: outputs collided"
            tested.append(fmt)
    assert tested, "no candidate formats were writable in this build"
    print(f"ok: unique file hash per run for formats: {', '.join(tested)}")


def test_seeded_file_is_reproducible_on_disk():
    data, rate = _tone()
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in.wav")
        _write(src, data, rate, fmt="WAV")
        a = os.path.join(tmp, "a.wav")
        b = os.path.join(tmp, "b.wav")
        uniquify_audio_file(src, a, seed=123, strength="strong")
        uniquify_audio_file(src, b, seed=123, strength="strong")
        with open(a, "rb") as fa, open(b, "rb") as fb:
            assert fa.read() == fb.read(), "seeded output should be byte-identical"
    print("ok: a fixed seed reproduces a byte-identical file on disk")


def test_default_output_path_keeps_extension():
    assert default_output_path("song.mp3") == "song.unique.mp3"
    assert default_output_path("a/b/clip.flac") == os.path.join("a", "b", "clip.unique.flac")
    print("ok: default output path preserves the original extension")


if __name__ == "__main__":
    test_perturb_changes_but_stays_close()
    test_strong_adds_leading_pad()
    test_seed_reproducible_and_diverges()
    test_roundtrip_unique_hash_per_format()
    test_seeded_file_is_reproducible_on_disk()
    test_default_output_path_keeps_extension()
    print("\nall tests passed")
