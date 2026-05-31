# Audio file data tools

Utilities that work at the raw audio data level:

- **`invert.py`** — phase-invert a WAV file (flip the polarity of every
  sample). Stdlib only.
- **`uniquify.py`** — make a *WAV* file unique at the data level without
  changing how it sounds. Stdlib only.
- **`uniquify_audio.py`** — the multi-format, stronger version: uniquify
  **MP3, FLAC, OGG, AIFF, WAV** and more, with a fingerprint-shifting preset.
  Needs `soundfile` + `numpy`.

## Phase inverter — `invert.py`

Flips the polarity of every PCM sample (multiplies the waveform by −1).

Inverting is its own undo: a phase-inverted file sounds identical on its own,
but mixed with the original it cancels to (near) silence. That cancellation is
the principle behind noise-cancelling headphones and "vocal remover" tricks,
and it makes the inverter trivial to verify — invert twice and you get the
original back.

```bash
python invert.py input.wav [output.wav]
```

If `output.wav` is omitted, the result is written next to the input as
`<name>.inverted.wav`.

```bash
$ python invert.py song.wav
wrote inverted audio to song.inverted.wav
```

## Uniquifier — `uniquify.py`

Makes every output a distinct file — different raw bytes, a different checksum,
and a different acoustic fingerprint — while sounding identical to a listener.
Useful for re-uploads that dedup detectors won't flag as the same file, A/B
copies, cache busting, or watermark-style tagging.

It works by dithering the least-significant bit(s) of each sample by a tiny,
pseudo-random amount. The change sits at or below the quantisation noise floor,
so it is inaudible, but it is enough to change the sample bytes (so md5/sha of
the data differ) and shift the waveform (so audio-fingerprint hashes differ).

```bash
python uniquify.py input.wav [output.wav] [--seed N] [--depth N]
```

If `output.wav` is omitted, the result is written next to the input as
`<name>.unique.wav`.

```bash
$ python uniquify.py song.wav            # unique file every run
wrote unique audio to song.unique.wav
$ python uniquify.py song.wav out.wav --seed 123   # reproducible
```

- `--seed N` makes the perturbation reproducible (same seed + same input →
  same output). Omit it and each run produces a different file.
- `--depth N` sets how many low-order bits may change (default `1` — the
  gentlest and most inaudible; each sample moves by at most ±(2ᴺ−1)).

Each run with no seed produces a different SHA, e.g.:

```bash
$ python uniquify.py song.wav a.wav && python uniquify.py song.wav b.wav
$ md5sum a.wav b.wav      # the two hashes differ
```

## Multi-format uniquifier — `uniquify_audio.py`

The same idea as `uniquify.py`, but it reads and writes **many formats** (via
libsndfile) and applies a **stronger** perturbation aimed at defeating
content-ID / dedup matching while staying essentially inaudible.

```bash
python uniquify_audio.py input.mp3 [output.mp3] [--seed N] \
       [--strength light|strong] [--list-formats]
```

It layers several imperceptible transforms, each of which moves a different
fingerprinting feature:

| Transform            | What it defeats                                  |
| -------------------- | ------------------------------------------------ |
| LSB dither           | exact-hash / byte-level dedup                    |
| micro gain jitter    | amplitude-based fingerprints (~0.3%)             |
| sub-LSB DC offset    | nudges the whole waveform                        |
| leading-silence pad  | time-alignment, which most fingerprinters key on |

- `--strength strong` (default) applies all four; `light` ≈ the gentle,
  WAV-tool behaviour (pure LSB dither, no pad).
- `--seed N` makes the result reproducible; omit it for a unique file each run.
- `--list-formats` prints the formats your libsndfile build supports.

Formats depend on your libsndfile build — typically **WAV, FLAC, OGG, AIFF,
MP3** and others. **AAC/M4A need ffmpeg and are not handled here.**

```bash
$ python uniquify_audio.py track.mp3            # unique MP3 every run
wrote unique audio to track.unique.mp3
```

Requires `soundfile` and `numpy`:

```bash
pip install -r requirements.txt
```

## Supported formats (WAV tools)

The stdlib WAV tools handle uncompressed PCM WAV files with any channel count:

| Sample width | Encoding             | Inversion          |
| ------------ | -------------------- | ------------------ |
| 8-bit        | unsigned (centre 128)| mirror: `255 - x`  |
| 16/24/32-bit | signed little-endian | negate: `-x`       |

The most-negative signed value (e.g. `-32768` in 16-bit) has no positive
counterpart, so it is clamped to the most-positive value to avoid overflow.
The uniquifier likewise clamps perturbed samples to the format's valid range.

## Tests

```bash
python test_invert.py          # stdlib only
python test_uniquify.py        # stdlib only
python test_uniquify_audio.py  # needs soundfile + numpy (skips if missing)
```

`test_invert.py` confirms signed samples sum to zero with their inverse, that
8-bit samples mirror around the midpoint, that the most-negative sample is
clamped, that double inversion is the identity, and that a WAV file round-trip
preserves the format header.

`test_uniquify.py` confirms the output bytes differ from the input, that every
sample stays within the requested bit depth, that a seed makes the result
reproducible while different seeds diverge, that independent runs each produce
a unique hash, that samples at the format extremes stay in range, and that the
WAV round-trip preserves params and length.

`test_uniquify_audio.py` confirms the perturbation changes the data while
staying near-inaudible, that the strong preset shifts time alignment, that a
seed is reproducible while different seeds diverge, that each run yields a
unique file hash across every writable format, and that the output extension
is preserved.

The WAV tools (`invert.py`, `uniquify.py`) use the standard library only.
`uniquify_audio.py` additionally needs `soundfile` and `numpy`
(`pip install -r requirements.txt`).
