#!/usr/bin/env python3
"""Make an audio file unique at the data level across many formats.

This is the heavier sibling of ``uniquify.py``. Where that module is
stdlib-only and WAV-only, this one uses ``soundfile`` (libsndfile) + ``numpy``
to read and write MP3, FLAC, OGG, AIFF, WAV and more, and applies a *stronger*
fingerprint-shifting perturbation aimed at defeating content-ID / dedup
matching while staying essentially inaudible.

The goal is the same: every output is a distinct file — different bytes,
different checksum, and a meaningfully different acoustic fingerprint — yet it
sounds like the original to a listener.

How "stronger" works. Instead of only dithering the least-significant bit, it
layers several imperceptible transforms, each of which moves a different
fingerprinting feature:

  * LSB dither           — randomises sample bytes (defeats exact-hash dedup)
  * micro gain jitter    — tiny per-file volume change (~0.3%)
  * DC / sub-LSB offset  — shifts the waveform a hair
  * leading-silence pad  — a few ms of near-silence shifts time alignment,
                           which is what most audio fingerprinters key on

A ``--seed`` makes all of this reproducible; omit it for a unique file each
run. ``--strength`` selects a preset: ``subtle`` (≈ the stdlib LSB-only
behaviour), ``normal`` (the default), or ``high`` (most fingerprint
divergence). All three stay below what a casual listener would notice.

Formats: whatever your libsndfile build supports (run with --list-formats).
AAC/M4A need ffmpeg and are not handled here.

Pass ``--metadata`` to also make the file unique at the *tag* level: a random
id is embedded in the comment/software fields (existing tags are preserved
unless ``--no-preserve-tags`` is given). This helps against dedup that keys on
metadata rather than the audio itself.

Usage:
    python uniquify_audio.py input.mp3 [output.mp3] [--seed N]
                             [--strength subtle|normal|high]
                             [--metadata [--no-preserve-tags]] [--list-formats]

If output is omitted the result is written next to the input as
"<name>.unique<ext>", preserving the original format.
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


# Preset perturbation parameters. Amounts are deliberately tiny: at 16-bit,
# one quantisation step is ~1/32768, so a few steps of dither and a sub-percent
# gain change sit at or below the noise floor.
PRESETS = {
    # "subtle" mirrors the gentle, near-pure-LSB behaviour of uniquify.py:
    # the smallest possible change that still makes the file unique.
    "subtle": {
        "dither_steps": 1.0,    # +/- this many quantisation steps of noise
        "gain_jitter": 0.0,     # fraction, e.g. 0.003 == 0.3%
        "offset_steps": 0.0,    # constant DC offset in quantisation steps
        "pad_ms_max": 0.0,      # up to this many ms of leading near-silence
    },
    # "normal" (the default) layers a few imperceptible shifts to move more
    # fingerprint features while remaining inaudible.
    "normal": {
        "dither_steps": 2.0,
        "gain_jitter": 0.003,
        "offset_steps": 0.5,
        "pad_ms_max": 8.0,
    },
    # "high" pushes each transform harder for the most fingerprint divergence,
    # still well below what a casual listener would notice.
    "high": {
        "dither_steps": 4.0,
        "gain_jitter": 0.008,
        "offset_steps": 1.0,
        "pad_ms_max": 25.0,
    },
}


def _quant_step(subtype: str) -> float:
    """Approximate one quantisation step for a libsndfile subtype, in the
    [-1, 1] float domain soundfile uses. Falls back to 16-bit if unknown."""
    bits = 16
    for n in (8, 16, 24, 32):
        if str(n) in subtype:
            bits = n
            break
    return 1.0 / (1 << (bits - 1))


def perturb(
    samples,  # np.ndarray, shape (frames,) or (frames, channels), float
    samplerate: int,
    rng,  # np.random.Generator
    preset: dict,
    subtype: str = "PCM_16",
):
    """Return a perturbed copy of `samples` according to `preset`.

    `samples` is the float array soundfile returns. The output has the same
    dtype and channel layout, possibly with a few leading frames of
    near-silence prepended (which is what shifts time-based fingerprints).
    """
    step = _quant_step(subtype)
    out = np.array(samples, dtype=np.float64, copy=True)

    # 1) micro gain jitter — a single tiny multiplier for the whole file.
    if preset["gain_jitter"] > 0:
        g = 1.0 + float(rng.uniform(-preset["gain_jitter"], preset["gain_jitter"]))
        out *= g

    # 2) constant sub-LSB DC offset — nudges the whole waveform.
    if preset["offset_steps"] > 0:
        out += float(rng.uniform(-1, 1)) * preset["offset_steps"] * step

    # 3) per-sample dither — randomises the low bits of every sample.
    if preset["dither_steps"] > 0:
        amp = preset["dither_steps"] * step
        out += rng.uniform(-amp, amp, size=out.shape)

    out = np.clip(out, -1.0, 1.0)

    # 4) leading near-silence pad — a few ms shifts time alignment.
    if preset["pad_ms_max"] > 0 and samplerate > 0:
        pad_frames = int(rng.integers(1, max(2, int(samplerate * preset["pad_ms_max"] / 1000.0))))
        if out.ndim == 1:
            pad = rng.uniform(-step, step, size=pad_frames)
        else:
            pad = rng.uniform(-step, step, size=(pad_frames, out.shape[1]))
        out = np.concatenate([pad, out], axis=0)

    return out.astype(np.float64)


def _unique_id(rng) -> str:
    """A random, file-unique identifier suitable for embedding in a tag."""
    # 16 random bytes as hex -> collision-proof in practice, like a UUID4.
    return rng.integers(0, 256, size=16, dtype=np.uint8).tobytes().hex()


def build_metadata(source_tags: dict, rng, preserve: bool = True) -> dict:
    """Return a tag dict that is unique per call.

    A fresh random id is written into the `comment` field (and prefixed onto
    `software`) so two outputs of the same source differ at the metadata level
    as well as the data level. When `preserve` is true, the source's existing
    tags are carried over first (libsndfile otherwise drops them).
    """
    tags = dict(source_tags) if preserve else {}
    uid = _unique_id(rng)
    tags["comment"] = f"uniquify-id:{uid}"
    base_software = tags.get("software", "").split(" (")[0]
    tags["software"] = f"{base_software + ' ' if base_software else ''}uniquify[{uid[:8]}]"
    return tags


def uniquify_audio_file(
    input_path: str,
    output_path: str,
    seed: int | None = None,
    strength: str = "normal",
    metadata: bool = False,
    preserve_tags: bool = True,
) -> None:
    """Read any libsndfile-readable audio file, perturb it so it is unique,
    and write it back in the same format/subtype.

    When `metadata` is true the output also gets a unique id embedded in its
    tags (and, by default, the source's existing tags preserved), so the file
    is unique at the metadata level too — useful against dedup that keys on
    tags rather than audio. The same `seed` reproduces the same id.
    """
    if sf is None:
        raise RuntimeError(
            "soundfile and numpy are required for multi-format support; "
            f"install them (pip install soundfile numpy). Original error: {_IMPORT_ERROR}"
        )
    if strength not in PRESETS:
        choices = ", ".join(sorted(PRESETS))
        raise ValueError(f"unknown strength: {strength!r} (choose one of: {choices})")

    rng = np.random.default_rng(seed)  # seed=None -> OS entropy, unique each run

    data, samplerate = sf.read(input_path, always_2d=False)
    info = sf.info(input_path)

    perturbed = perturb(data, samplerate, rng, PRESETS[strength], info.subtype)

    with sf.SoundFile(output_path, "w", samplerate=samplerate,
                      channels=1 if perturbed.ndim == 1 else perturbed.shape[1],
                      format=info.format, subtype=info.subtype) as out:
        if metadata:
            src_tags = sf.SoundFile(input_path).copy_metadata()
            for key, value in build_metadata(src_tags, rng, preserve_tags).items():
                try:
                    setattr(out, key, value)
                except (AttributeError, RuntimeError):
                    pass  # tag unsupported for this format; skip quietly
        out.write(perturbed)


def default_output_path(input_path: str) -> str:
    root, ext = os.path.splitext(input_path)
    return f"{root}.unique{ext or '.wav'}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Make an audio file unique at the data level (multi-format)."
    )
    parser.add_argument("input", nargs="?", help="path to the input audio file")
    parser.add_argument(
        "output",
        nargs="?",
        help="path to write the unique file (default: <name>.unique<ext>)",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="seed for reproducible output (default: random each run)",
    )
    parser.add_argument(
        "--strength", choices=sorted(PRESETS), default="normal",
        help="perturbation preset: subtle, normal, or high (default: normal)",
    )
    parser.add_argument(
        "--metadata", action="store_true",
        help="also make the file unique at the metadata level by embedding a "
             "random id in its tags (preserves existing tags by default)",
    )
    parser.add_argument(
        "--no-preserve-tags", action="store_true",
        help="with --metadata, drop the source's existing tags instead of "
             "carrying them over",
    )
    parser.add_argument(
        "--list-formats", action="store_true",
        help="list audio formats supported by this libsndfile build and exit",
    )
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
        uniquify_audio_file(
            args.input, output, seed=args.seed, strength=args.strength,
            metadata=args.metadata, preserve_tags=not args.no_preserve_tags,
        )
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"wrote unique audio to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
