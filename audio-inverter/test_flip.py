#!/usr/bin/env python3
"""Tests for the audio flipper.

Run with: python test_flip.py

Requires soundfile + numpy. If they are unavailable the suite skips with a
clear message rather than failing, so the stdlib-only tests can still run in
minimal environments.
"""

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

from flip import (
    time_stretch,
    resample_linear,
    pitch_shift,
    fft_filter,
    saturate,
    widen,
    flip,
    flip_audio_file,
    default_output_path,
    DEFAULTS,
)


def _tone(seconds=1.0, rate=22050, freq=440.0):
    t = np.arange(int(seconds * rate)) / rate
    return (0.5 * np.sin(2 * math.pi * freq * t)).astype(np.float64), rate


def _dominant_freq(x, rate):
    """Return the frequency of the largest spectral peak."""
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    freqs = np.fft.rfftfreq(len(x), d=1.0 / rate)
    return freqs[int(np.argmax(spec))]


def _check(name, cond):
    print(f"{'ok' if cond else 'FAIL'}: {name}")
    if not cond:
        _check.failed += 1
_check.failed = 0


def test_time_stretch_changes_length_not_pitch():
    x, rate = _tone(seconds=1.0, freq=440.0)
    slow = time_stretch(x, 1.5)
    fast = time_stretch(x, 0.5)
    _check("time_stretch 1.5x is ~1.5x longer",
           abs(len(slow) / len(x) - 1.5) < 0.05)
    _check("time_stretch 0.5x is ~0.5x shorter",
           abs(len(fast) / len(x) - 0.5) < 0.05)
    # pitch (dominant frequency) should be preserved within a bin or two.
    _check("time_stretch preserves pitch",
           abs(_dominant_freq(slow, rate) - 440.0) < 25)


def test_resample_linear_length():
    x, _ = _tone(seconds=0.5)
    up = resample_linear(x, 2.0)
    down = resample_linear(x, 0.5)
    _check("resample 2x doubles length", len(up) == 2 * len(x) or len(up) == 2 * len(x) - 1 or abs(len(up) - 2 * len(x)) <= 1)
    _check("resample 0.5x halves length", abs(len(down) - len(x) // 2) <= 1)


def test_pitch_shift_moves_pitch_keeps_length():
    x, rate = _tone(seconds=1.0, freq=440.0)
    up = pitch_shift(x, 12.0)    # up an octave -> ~880 Hz
    down = pitch_shift(x, -12.0)  # down an octave -> ~220 Hz
    _check("pitch_shift preserves length (+12)", abs(len(up) - len(x)) <= 2)
    _check("pitch_shift preserves length (-12)", abs(len(down) - len(x)) <= 2)
    # Full-octave shifts are the extreme case; linear-resample spectral error
    # is largest here, so allow a wider tolerance than a musical flip needs.
    _check("pitch_shift +12 ~doubles frequency",
           abs(_dominant_freq(up, rate) - 880.0) < 60)
    _check("pitch_shift -12 ~halves frequency",
           abs(_dominant_freq(down, rate) - 220.0) < 60)


def test_pitch_shift_zero_is_identity():
    x, _ = _tone(seconds=0.3)
    out = pitch_shift(x, 0.0)
    _check("pitch_shift 0 is identity", np.allclose(out, x))


def test_fft_filter_attenuates_band():
    rate = 22050
    t = np.arange(rate) / rate
    low = np.sin(2 * math.pi * 100 * t)
    high = np.sin(2 * math.pi * 8000 * t)
    mix = (low + high) * 0.4
    lp = fft_filter(mix, rate, highpass=None, lowpass=2000.0)
    hp = fft_filter(mix, rate, highpass=2000.0, lowpass=None)
    _check("lowpass keeps 100 Hz energy",
           np.abs(np.fft.rfft(lp))[100] > 0.2 * np.abs(np.fft.rfft(mix))[100])
    _check("lowpass cuts 8000 Hz energy",
           np.abs(np.fft.rfft(lp))[8000] < 0.2 * np.abs(np.fft.rfft(mix))[8000])
    _check("highpass cuts 100 Hz energy",
           np.abs(np.fft.rfft(hp))[100] < 0.2 * np.abs(np.fft.rfft(mix))[100])


def test_fft_filter_disabled_is_identity():
    x, _ = _tone(seconds=0.3)
    _check("fft_filter with no cutoffs is identity",
           np.allclose(fft_filter(x, 22050, None, None), x))


def test_saturate_adds_harmonics_and_bounds():
    x, rate = _tone(seconds=0.5, freq=300.0)
    sat = saturate(x, 1.5)
    _check("saturate stays within [-1, 1]", np.max(np.abs(sat)) <= 1.0 + 1e-9)
    # a 3rd harmonic (900 Hz) should appear that was not in the pure tone.
    spec = np.abs(np.fft.rfft(sat))
    freqs = np.fft.rfftfreq(len(sat), d=1.0 / rate)
    h3 = spec[np.argmin(np.abs(freqs - 900.0))]
    _check("saturate introduces a harmonic", h3 > 1e-3 * spec.max())
    _check("saturate 0 is identity", np.allclose(saturate(x, 0.0), x))


def test_widen_changes_side_only():
    rate = 22050
    t = np.arange(rate // 2) / rate
    left = np.sin(2 * math.pi * 440 * t)
    right = np.sin(2 * math.pi * 440 * t + 0.5)
    stereo = np.stack([left, right], axis=1) * 0.4
    wide = widen(stereo, 1.5)
    mid_in = (stereo[:, 0] + stereo[:, 1]) * 0.5
    mid_out = (wide[:, 0] + wide[:, 1]) * 0.5
    side_in = (stereo[:, 0] - stereo[:, 1]) * 0.5
    side_out = (wide[:, 0] - wide[:, 1]) * 0.5
    _check("widen preserves mid (mono) content", np.allclose(mid_in, mid_out))
    _check("widen scales the side channel",
           np.allclose(side_out, side_in * 1.5))
    _check("widen 1.0 is identity", np.allclose(widen(stereo, 1.0), stereo))


def test_flip_mono_recognisable_but_different():
    x, rate = _tone(seconds=1.0, freq=440.0)
    rng = np.random.default_rng(0)
    params = dict(DEFAULTS)
    out = flip(x, rate, params, rng)
    _check("flip mono produces output", out.size > 0)
    _check("flip keeps length within ~10%",
           abs(len(out) / len(x) - 1.0) < 0.12)
    _check("flip stays within [-1, 1]", np.max(np.abs(out)) <= 1.0 + 1e-9)
    # default is -2 semitones from 440 -> ~392 Hz; clearly moved but nearby.
    df = _dominant_freq(out, rate)
    _check("flip shifts pitch down toward the chosen key (~392 Hz)",
           360 < df < 420)


def test_flip_stereo_shape_preserved():
    x, rate = _tone(seconds=0.8, freq=440.0)
    stereo = np.stack([x, x], axis=1)
    rng = np.random.default_rng(1)
    out = flip(stereo, rate, dict(DEFAULTS), rng)
    _check("flip stereo stays 2-channel", out.ndim == 2 and out.shape[1] == 2)


def test_seed_reproducible_and_varies():
    x, rate = _tone(seconds=0.6, freq=440.0)
    a = flip(x, rate, dict(DEFAULTS), np.random.default_rng(42))
    b = flip(x, rate, dict(DEFAULTS), np.random.default_rng(42))
    c = flip(x, rate, dict(DEFAULTS), np.random.default_rng(43))
    n = min(len(a), len(b), len(c))
    _check("same seed -> identical flip", np.allclose(a[:n], b[:n]))
    _check("different seed -> different flip", not np.allclose(a[:n], c[:n]))


def test_file_roundtrip_and_default_name():
    x, rate = _tone(seconds=0.5, freq=440.0)
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "song.wav")
        sf.write(src, x, rate)
        out = default_output_path(src)
        _check("default output name is <name>.flip.wav",
               out.endswith("song.flip.wav"))
        flip_audio_file(src, out, seed=7)
        _check("flip file was written", os.path.exists(out))
        data, sr = sf.read(out)
        _check("flipped file is readable audio", data.size > 0 and sr == rate)


def main():
    test_time_stretch_changes_length_not_pitch()
    test_resample_linear_length()
    test_pitch_shift_moves_pitch_keeps_length()
    test_pitch_shift_zero_is_identity()
    test_fft_filter_attenuates_band()
    test_fft_filter_disabled_is_identity()
    test_saturate_adds_harmonics_and_bounds()
    test_widen_changes_side_only()
    test_flip_mono_recognisable_but_different()
    test_flip_stereo_shape_preserved()
    test_seed_reproducible_and_varies()
    test_file_roundtrip_and_default_name()

    if _check.failed:
        print(f"\n{_check.failed} check(s) failed")
        return 1
    print("\nall flip tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
