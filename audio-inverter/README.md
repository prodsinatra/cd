# Audio file data inverter

A tiny, dependency-free WAV **phase inverter**. It flips the polarity of every
PCM sample (multiplies the waveform by −1).

Inverting is its own undo: a phase-inverted file sounds identical on its own,
but mixed with the original it cancels to (near) silence. That cancellation is
the principle behind noise-cancelling headphones and "vocal remover" tricks,
and it makes the inverter trivial to verify — invert twice and you get the
original back.

## Usage

```bash
python invert.py input.wav [output.wav]
```

If `output.wav` is omitted, the result is written next to the input as
`<name>.inverted.wav`.

```bash
$ python invert.py song.wav
wrote inverted audio to song.inverted.wav
```

## Supported formats

Uncompressed PCM WAV files with any channel count:

| Sample width | Encoding             | Inversion          |
| ------------ | -------------------- | ------------------ |
| 8-bit        | unsigned (centre 128)| mirror: `255 - x`  |
| 16/24/32-bit | signed little-endian | negate: `-x`       |

The most-negative signed value (e.g. `-32768` in 16-bit) has no positive
counterpart, so it is clamped to the most-positive value to avoid overflow.

## Tests

```bash
python test_invert.py
```

The tests generate tones in memory, confirm signed samples sum to zero with
their inverse, that 8-bit samples mirror around the midpoint, that the
most-negative sample is clamped, that double inversion is the identity, and
that a full WAV file round-trip preserves the format header.

Standard library only (`wave`, `argparse`) — no external dependencies.
