#!/usr/bin/env python3
"""Make a WAV file unique at the data level without changing how it sounds.

Sometimes you need every copy of an audio file to be a *distinct* file —
different bytes, a different checksum, a different acoustic fingerprint — even
though it should still sound the same to a listener (re-uploads that dedup
detectors won't flag as identical, A/B copies, watermark-style tagging, cache
busting, etc.).

This does that by dithering the least-significant bit(s) of each PCM sample by
a tiny, pseudo-random amount. The change is at or below the noise floor, so it
is inaudible, but it is enough to:

  * change the raw sample bytes (so md5/sha of the data differ),
  * shift the waveform so audio-fingerprint hashes differ.

A `--seed` makes the perturbation reproducible (same seed + same input ->
same output); omit it and each run is unique. `--depth` controls how many
low-order bits may change (1 = gentlest/most inaudible, the default).

Standard library only. Handles 8/16/24/32-bit PCM, any channel count.

Usage:
    python uniquify.py input.wav [output.wav] [--seed N] [--depth N]

If output.wav is omitted, the result is written next to the input as
"<name>.unique.wav".
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import wave


def uniquify_samples(
    frames: bytes,
    sample_width: int,
    rng: random.Random,
    depth: int = 1,
) -> bytes:
    """Return PCM `frames` with each sample nudged by a tiny random amount.

    `depth` is the number of low-order bits that may change: each sample is
    shifted by a random delta in the range [-(2**depth - 1), +(2**depth - 1)],
    then clamped to the format's valid range. With depth=1 that delta is just
    -1, 0, or +1 — at or below the quantisation noise floor, so inaudible.
    """
    if depth < 1:
        raise ValueError("depth must be at least 1")
    if sample_width not in (1, 2, 3, 4):
        raise ValueError(f"unsupported sample width: {sample_width} bytes")

    spread = (1 << depth) - 1  # depth=1 -> 1, depth=2 -> 3, ...

    if sample_width == 1:
        # 8-bit WAV PCM is unsigned, range 0..255.
        lo, hi = 0, 255
        out = bytearray(len(frames))
        for i, b in enumerate(frames):
            delta = rng.randint(-spread, spread)
            out[i] = max(lo, min(hi, b + delta))
        return bytes(out)

    # Signed little-endian for 16/24/32-bit.
    lo = -(1 << (sample_width * 8 - 1))
    hi = (1 << (sample_width * 8 - 1)) - 1
    out = bytearray(len(frames))
    for i in range(0, len(frames), sample_width):
        value = int.from_bytes(frames[i:i + sample_width], "little", signed=True)
        delta = rng.randint(-spread, spread)
        value = max(lo, min(hi, value + delta))
        out[i:i + sample_width] = value.to_bytes(
            sample_width, "little", signed=True
        )
    return bytes(out)


def uniquify_file(
    input_path: str,
    output_path: str,
    seed: int | None = None,
    depth: int = 1,
) -> None:
    """Read a WAV file, perturb its data so it is unique, and write it out.

    When `seed` is None the perturbation is drawn from os.urandom, so every
    run produces a different file. Passing a seed makes the result
    reproducible for the same input.
    """
    rng = random.Random(seed) if seed is not None else random.Random(os.urandom(16))

    with wave.open(input_path, "rb") as src:
        params = src.getparams()
        frames = src.readframes(params.nframes)

    unique = uniquify_samples(frames, params.sampwidth, rng, depth)

    with wave.open(output_path, "wb") as dst:
        dst.setparams(params)
        dst.writeframes(unique)


def default_output_path(input_path: str) -> str:
    if input_path.lower().endswith(".wav"):
        return input_path[:-4] + ".unique.wav"
    return input_path + ".unique.wav"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Make a WAV file unique at the data level without changing "
                    "how it sounds."
    )
    parser.add_argument("input", help="path to the input .wav file")
    parser.add_argument(
        "output",
        nargs="?",
        help="path to write the unique .wav (default: <name>.unique.wav)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="seed for reproducible output (default: random each run)",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=1,
        help="number of low-order bits that may change (default: 1, inaudible)",
    )
    args = parser.parse_args(argv)

    output = args.output or default_output_path(args.input)

    try:
        uniquify_file(args.input, output, seed=args.seed, depth=args.depth)
    except (wave.Error, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"wrote unique audio to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
