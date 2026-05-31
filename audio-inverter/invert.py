#!/usr/bin/env python3
"""Phase-invert the audio data in a WAV file.

Phase inversion flips the polarity of every PCM sample (multiplying the
waveform by -1). The result sounds identical on its own, but summed with the
original it cancels to (near) silence — the classic test of a correct
inverter and the building block behind noise-cancellation and "vocal
remover" tricks.

This is a self-contained demo: it only uses the Python standard library and
handles the common uncompressed PCM formats (8/16/24/32-bit, any number of
channels).

Usage:
    python invert.py input.wav output.wav

If output.wav is omitted, the inverted file is written next to the input as
"<name>.inverted.wav".
"""

from __future__ import annotations

import argparse
import sys
import wave


def invert_samples(frames: bytes, sample_width: int) -> bytes:
    """Return PCM `frames` with every sample's polarity flipped.

    Signed formats (16/24/32-bit) are negated; 8-bit WAV PCM is unsigned and
    centred on 128, so it is mirrored around that midpoint instead.
    """
    if sample_width == 1:
        # 8-bit PCM is unsigned with a midpoint of 128: mirror around it.
        # 255 - x maps 0<->255 and keeps the midpoint stable enough.
        return bytes(255 - b for b in frames)

    if sample_width not in (2, 3, 4):
        raise ValueError(f"unsupported sample width: {sample_width} bytes")

    out = bytearray(len(frames))
    lo = -(1 << (sample_width * 8 - 1))  # most negative value, e.g. -32768
    hi = (1 << (sample_width * 8 - 1)) - 1  # most positive value, e.g. 32767

    for i in range(0, len(frames), sample_width):
        chunk = frames[i:i + sample_width]
        value = int.from_bytes(chunk, byteorder="little", signed=True)
        # Negating the most-negative value would overflow the range, so clamp.
        value = max(lo, min(hi, -value))
        out[i:i + sample_width] = value.to_bytes(
            sample_width, byteorder="little", signed=True
        )

    return bytes(out)


def invert_file(input_path: str, output_path: str) -> None:
    """Read a WAV file, invert its audio data, and write the result."""
    with wave.open(input_path, "rb") as src:
        params = src.getparams()
        frames = src.readframes(params.nframes)

    inverted = invert_samples(frames, params.sampwidth)

    with wave.open(output_path, "wb") as dst:
        dst.setparams(params)
        dst.writeframes(inverted)


def default_output_path(input_path: str) -> str:
    if input_path.lower().endswith(".wav"):
        return input_path[:-4] + ".inverted.wav"
    return input_path + ".inverted.wav"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase-invert the audio data in a WAV file."
    )
    parser.add_argument("input", help="path to the input .wav file")
    parser.add_argument(
        "output",
        nargs="?",
        help="path to write the inverted .wav (default: <name>.inverted.wav)",
    )
    args = parser.parse_args(argv)

    output = args.output or default_output_path(args.input)

    try:
        invert_file(args.input, output)
    except (wave.Error, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"wrote inverted audio to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
