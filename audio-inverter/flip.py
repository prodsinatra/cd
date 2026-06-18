#!/usr/bin/env python3
"""Make a *new, audibly distinct version* of a track that still sounds like
itself — a "flip".

Where ``uniquify_audio.py`` changes the bytes while keeping the sound
identical, this tool deliberately changes the *sound* in musical ways while
keeping the overall identity — the melody, the arrangement, the vibe — clearly
recognisable. The result is a different render you would call "the same song,
flipped", not a copy.

It layers four classic flip moves, each independently controllable:

  * pitch shift   — move the key by N semitones WITHOUT changing tempo
                    (phase-vocoder time-stretch + resample), so the melody is
                    preserved at a new pitch.
  * tempo change  — speed up / slow down WITHOUT changing pitch (phase
                    vocoder), so the groove changes but the key does not.
  * filtering     — gentle high-pass / low-pass roll-off (FFT domain) to
                    reshape the tone, the way a flip often filters the sample.
  * saturation    — light tanh drive for analog-style warmth/grit.

Pitch and tempo are independent on purpose: that is what separates a musical
flip from naively changing playback speed (which drags pitch and tempo
together and just sounds like a tape running fast).

A ``--seed`` makes the small per-run variation reproducible; omit it and every
run is a slightly different flip. Defaults give a noticeable-but-recognisable
flip (down a whole step, a touch slower, lightly filtered and saturated).

Formats: whatever your libsndfile build supports (run with --list-formats).
AAC/M4A need ffmpeg and are not handled here.

Usage:
    python flip.py input.mp3 [output.mp3]
        [--semitones N] [--tempo F] [--highpass HZ] [--lowpass HZ]
        [--drive F] [--width F] [--seed N] [--list-formats]

If output is omitted the result is written next to the input as
"<name>.flip<ext>", preserving the original format.
"""

from __future__ import annotations

import argparse
import os
import sys

try:
    import numpy as np
    import soundfile as sf
except ImportError as exc:  # pragma: no cover - exercised via CLI message
    np = None
    sf = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


# Defaults chosen to read as a "noticeable flip": a recognisably different
# version whose core melody/sound is still obviously the source track.
DEFAULTS = {
    "semitones": -2.0,   # down a whole step
    "tempo": 0.97,       # ~3% slower (pitch unaffected)
    "highpass": 30.0,    # Hz, trims sub rumble
    "lowpass": 15000.0,  # Hz, gentle top roll-off
    "drive": 0.8,        # tanh saturation amount (0 = none)
    "width": 1.12,       # stereo widening factor (1.0 = unchanged)
}


def time_stretch(x, stretch: float, n_fft: int = 2048, hop: int = 256):
    """Phase-vocoder time-stretch of a mono signal.

    ``stretch`` > 1 makes the signal longer (slower); < 1 shorter (faster).
    Pitch is preserved. Returns a float64 array roughly ``len(x) * stretch``
    samples long.
    """
    x = np.asarray(x, dtype=np.float64)
    if abs(stretch - 1.0) < 1e-9 or len(x) < n_fft:
        return x.copy()

    win = np.hanning(n_fft).astype(np.float64)
    ana_hop = hop
    syn_hop = int(round(hop * stretch))
    nbins = n_fft // 2 + 1
    # Expected phase advance per analysis hop for each bin centre.
    omega = 2.0 * np.pi * ana_hop * np.arange(nbins) / n_fft

    n_frames = 1 + (len(x) - n_fft) // ana_hop
    out_len = n_fft + syn_hop * (n_frames - 1)
    out = np.zeros(out_len, dtype=np.float64)
    win_sum = np.zeros(out_len, dtype=np.float64)

    last_phase = np.zeros(nbins)
    acc_phase = np.zeros(nbins)
    ratio = syn_hop / ana_hop

    for i in range(n_frames):
        a0 = i * ana_hop
        frame = x[a0:a0 + n_fft] * win
        spec = np.fft.rfft(frame)
        mag = np.abs(spec)
        phase = np.angle(spec)

        if i == 0:
            acc_phase = phase.copy()
        else:
            # principal-argument the deviation from the expected advance,
            # giving the true per-hop frequency, then advance the synthesis
            # phase by that true frequency scaled to the synthesis hop.
            dphi = phase - last_phase - omega
            dphi = np.mod(dphi + np.pi, 2.0 * np.pi) - np.pi
            true_freq = omega + dphi
            acc_phase = acc_phase + ratio * true_freq
        last_phase = phase

        synth = np.fft.irfft(mag * np.exp(1j * acc_phase), n_fft)
        s0 = i * syn_hop
        out[s0:s0 + n_fft] += synth * win
        win_sum[s0:s0 + n_fft] += win * win

    nz = win_sum > 1e-8
    out[nz] /= win_sum[nz]
    return out


def resample_linear(x, factor: float):
    """Linearly resample a mono signal to ``round(len(x) * factor)`` samples."""
    x = np.asarray(x, dtype=np.float64)
    n_out = max(1, int(round(len(x) * factor)))
    if n_out == len(x):
        return x.copy()
    src = np.arange(len(x))
    idx = np.linspace(0.0, len(x) - 1, n_out)
    return np.interp(idx, src, x)


def pitch_shift(x, semitones: float, n_fft: int = 2048, hop: int = 256):
    """Shift pitch by ``semitones`` while preserving duration.

    Stretch by the pitch ratio, then resample back to the original length:
    the net effect is a pitch change with the same timing.
    """
    x = np.asarray(x, dtype=np.float64)
    if abs(semitones) < 1e-9:
        return x.copy()
    ratio = 2.0 ** (semitones / 12.0)
    stretched = time_stretch(x, ratio, n_fft=n_fft, hop=hop)
    # Resample straight back to the original length so duration is preserved
    # exactly (stretch + factor rounding would otherwise drift a few samples).
    idx = np.linspace(0.0, len(stretched) - 1, len(x))
    return np.interp(idx, np.arange(len(stretched)), stretched)


def fft_filter(x, samplerate: int, highpass=None, lowpass=None):
    """Apply a gentle (≈2nd-order) high-pass and/or low-pass in the FFT domain."""
    if not highpass and not lowpass:
        return np.asarray(x, dtype=np.float64).copy()
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, d=1.0 / samplerate)
    resp = np.ones_like(freqs)
    if highpass:
        safe = np.maximum(freqs, 1e-6)
        resp *= 1.0 / (1.0 + (highpass / safe) ** 4)
    if lowpass:
        resp *= 1.0 / (1.0 + (freqs / lowpass) ** 4)
    return np.fft.irfft(spec * resp, n)


def saturate(x, amount: float):
    """Light tanh saturation. ``amount`` 0 = bypass; larger = more drive.

    Normalised so the transfer curve passes through ±1, keeping level roughly
    constant while adding harmonics.
    """
    if amount <= 0:
        return np.asarray(x, dtype=np.float64).copy()
    x = np.asarray(x, dtype=np.float64)
    k = 1.0 + amount
    return np.tanh(k * x) / np.tanh(k)


def widen(stereo, width: float):
    """Mid/side stereo widening for a (frames, 2) array. width 1.0 = unchanged."""
    if abs(width - 1.0) < 1e-9 or stereo.ndim != 2 or stereo.shape[1] != 2:
        return stereo
    left = stereo[:, 0]
    right = stereo[:, 1]
    mid = (left + right) * 0.5
    side = (left - right) * 0.5 * width
    out = np.empty_like(stereo)
    out[:, 0] = mid + side
    out[:, 1] = mid - side
    return out


def flip(samples, samplerate: int, params: dict, rng):
    """Return a flipped copy of ``samples`` (mono 1-D or (frames, channels)).

    Applies, per channel: pitch shift -> tempo stretch -> filtering ->
    saturation; then stereo widening across channels. Small seeded jitter is
    added to tempo and pitch so independent runs differ slightly.
    """
    arr = np.asarray(samples, dtype=np.float64)

    # Per-run micro-variation: a few cents of detune and ~0.5% tempo wobble,
    # so each flip is unique without disturbing the chosen character.
    detune = float(rng.uniform(-0.05, 0.05))           # semitones (~5 cents)
    tempo_jit = 1.0 + float(rng.uniform(-0.005, 0.005))
    semitones = params["semitones"] + detune
    tempo = params["tempo"] * tempo_jit
    # tempo > 1 == faster == shorter == time_stretch by 1/tempo.
    stretch = 1.0 / tempo if tempo > 0 else 1.0

    def process(channel):
        y = pitch_shift(channel, semitones)
        y = time_stretch(y, stretch)
        y = fft_filter(y, samplerate, params["highpass"], params["lowpass"])
        y = saturate(y, params["drive"])
        return y

    if arr.ndim == 1:
        out = process(arr)
    else:
        cols = [process(arr[:, c]) for c in range(arr.shape[1])]
        length = min(len(c) for c in cols)
        out = np.stack([c[:length] for c in cols], axis=1)
        out = widen(out, params["width"])

    # Guard against clipping introduced by the chain.
    peak = float(np.max(np.abs(out))) if out.size else 0.0
    if peak > 1.0:
        out = out / peak
    return out


def flip_audio_file(
    input_path: str,
    output_path: str,
    seed: int | None = None,
    semitones: float = DEFAULTS["semitones"],
    tempo: float = DEFAULTS["tempo"],
    highpass: float | None = DEFAULTS["highpass"],
    lowpass: float | None = DEFAULTS["lowpass"],
    drive: float = DEFAULTS["drive"],
    width: float = DEFAULTS["width"],
) -> None:
    """Read any libsndfile-readable audio file, flip it, and write it back in
    the same format/subtype."""
    if sf is None:
        raise RuntimeError(
            "soundfile and numpy are required; install them "
            f"(pip install soundfile numpy). Original error: {_IMPORT_ERROR}"
        )

    rng = np.random.default_rng(seed)  # seed=None -> OS entropy, unique each run
    data, samplerate = sf.read(input_path, always_2d=False)
    info = sf.info(input_path)

    params = {
        "semitones": semitones,
        "tempo": tempo,
        "highpass": highpass,
        "lowpass": lowpass,
        "drive": drive,
        "width": width,
    }
    flipped = flip(data, samplerate, params, rng)

    channels = 1 if flipped.ndim == 1 else flipped.shape[1]
    with sf.SoundFile(output_path, "w", samplerate=samplerate,
                      channels=channels, format=info.format,
                      subtype=info.subtype) as out:
        out.write(flipped)


def default_output_path(input_path: str) -> str:
    root, ext = os.path.splitext(input_path)
    return f"{root}.flip{ext or '.wav'}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Make a new, audibly distinct version of a track that still "
                    "sounds like itself (a flip)."
    )
    parser.add_argument("input", nargs="?", help="path to the input audio file")
    parser.add_argument("output", nargs="?",
                        help="path to write (default: <name>.flip<ext>)")
    parser.add_argument("--semitones", type=float, default=DEFAULTS["semitones"],
                        help=f"pitch shift in semitones (default: {DEFAULTS['semitones']})")
    parser.add_argument("--tempo", type=float, default=DEFAULTS["tempo"],
                        help=f">1 faster, <1 slower, pitch preserved "
                             f"(default: {DEFAULTS['tempo']})")
    parser.add_argument("--highpass", type=float, default=DEFAULTS["highpass"],
                        help="high-pass cutoff in Hz; 0 to disable")
    parser.add_argument("--lowpass", type=float, default=DEFAULTS["lowpass"],
                        help="low-pass cutoff in Hz; 0 to disable")
    parser.add_argument("--drive", type=float, default=DEFAULTS["drive"],
                        help="tanh saturation amount; 0 to disable")
    parser.add_argument("--width", type=float, default=DEFAULTS["width"],
                        help="stereo widening factor; 1.0 leaves width unchanged")
    parser.add_argument("--seed", type=int, default=None,
                        help="seed for reproducible per-run variation "
                             "(default: random each run)")
    parser.add_argument("--list-formats", action="store_true",
                        help="list audio formats supported by libsndfile and exit")
    args = parser.parse_args(argv)

    if args.list_formats:
        if sf is None:
            print(f"error: soundfile not available: {_IMPORT_ERROR}", file=sys.stderr)
            return 1
        for key, desc in sorted(sf.available_formats().items()):
            print(f"{key:8} {desc}")
        return 0

    if not args.input:
        parser.error("input is required (unless --list-formats)")

    output = args.output or default_output_path(args.input)

    try:
        flip_audio_file(
            args.input, output, seed=args.seed,
            semitones=args.semitones, tempo=args.tempo,
            highpass=args.highpass or None, lowpass=args.lowpass or None,
            drive=args.drive, width=args.width,
        )
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"wrote flipped audio to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
