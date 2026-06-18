# Audio file data tools

Utilities that work at the raw audio data level:

- **`invert.py`** — phase-invert a WAV file (flip the polarity of every
  sample). Stdlib only.
- **`uniquify.py`** — make a *WAV* file unique at the data level without
  changing how it sounds. Stdlib only.
- **`uniquify_audio.py`** — the multi-format, stronger version: uniquify
  **MP3, FLAC, OGG, AIFF, WAV** and more, with a fingerprint-shifting preset.
  Needs `soundfile` + `numpy`.
- **`flip.py`** — make a *new, audibly distinct version* of a track that still
  sounds like itself: pitch-shift, tempo change, filtering and saturation.
  Multi-format. Needs `soundfile` + `numpy`.

> `uniquify*` keep the sound **identical** and only change the bytes.
> `flip.py` deliberately changes the **sound** in musical ways while keeping
> the track recognisable — use it when you want a genuinely different render,
> not a copy.

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
       [--strength subtle|normal|high] [--list-formats]
```

It layers several imperceptible transforms, each of which moves a different
fingerprinting feature:

| Transform            | What it defeats                                  |
| -------------------- | ------------------------------------------------ |
| LSB dither           | exact-hash / byte-level dedup                    |
| micro gain jitter    | amplitude-based fingerprints (~0.3%)             |
| sub-LSB DC offset    | nudges the whole waveform                        |
| leading-silence pad  | time-alignment, which most fingerprinters key on |

- `--strength` chooses how hard to push, all three staying below what a
  casual listener would notice:
  - `subtle` — pure LSB dither, no pad (≈ the gentle WAV-tool behaviour)
  - `normal` — **default**; applies all four transforms moderately
  - `high` — all four pushed harder, for the most fingerprint divergence
- `--seed N` makes the result reproducible; omit it for a unique file each run.
- `--metadata` *also* makes the file unique at the **tag** level: a random id
  is embedded in the comment/software fields, so two outputs differ in their
  metadata as well as their audio. Existing tags are preserved unless you add
  `--no-preserve-tags`. (The same `--seed` reproduces the same id.) Useful
  against dedup that keys on metadata rather than the waveform.
- `--list-formats` prints the formats your libsndfile build supports.

Formats depend on your libsndfile build — typically **WAV, FLAC, OGG, AIFF,
MP3** and others. **AAC/M4A need ffmpeg and are not handled here.**

```bash
$ python uniquify_audio.py track.mp3            # unique MP3 every run
wrote unique audio to track.unique.mp3

$ python uniquify_audio.py track.mp3 --metadata # unique audio AND tags
wrote unique audio to track.unique.mp3
```

> Note: by default (without `--metadata`) only the audio data is changed, and
> libsndfile does not copy the source's tags — so plain runs come out with
> empty metadata. Use `--metadata` when you want tag-level uniqueness and tag
> preservation.

Requires `soundfile` and `numpy`:

```bash
pip install -r requirements.txt
```

## Flipper — `flip.py`

Makes a **new version of a track that still sounds like the original** — a
"flip". Unlike the uniquifiers (which keep the sound identical and only change
the bytes), this changes the *sound* in musical ways while keeping the melody,
arrangement and overall vibe clearly recognisable.

It layers four classic flip moves, each independently controllable:

| Transform   | What it does                                                       |
| ----------- | ------------------------------------------------------------------ |
| pitch shift | move the key by N semitones **without** changing tempo             |
| tempo       | speed up / slow down **without** changing pitch                    |
| filtering   | gentle high-pass / low-pass roll-off to reshape the tone           |
| saturation  | light tanh drive for analog-style warmth/grit                      |

Pitch and tempo are independent on purpose: that is what separates a musical
flip from naively changing playback speed (which drags pitch and tempo
together and just sounds like a tape running fast). Pitch-shift and
time-stretch use a phase vocoder; filtering is done in the FFT domain.

```bash
python flip.py input.mp3 [output.wav] \
       [--semitones N] [--tempo F] [--highpass HZ] [--lowpass HZ] \
       [--drive F] [--width F] [--subtype SUBTYPE] [--seed N] [--list-formats]
```

If `output` is omitted the result is written next to the input as
`<name>.flip.wav`. **Output defaults to WAV regardless of the input format**,
because that is the higher-quality choice: the flip is computed in floating
point and written straight to lossless 24-bit WAV, avoiding the second lossy
generation you'd get by re-encoding back to MP3. The container format follows
the output file's extension, so pass e.g. `out.flac` for FLAC.

- `--semitones` — pitch shift in semitones (default `-2`, down a whole step).
- `--tempo` — `>1` faster, `<1` slower, pitch preserved (default `0.97`).
- `--highpass` / `--lowpass` — cutoffs in Hz (default `30` / `15000`); pass `0`
  to disable either.
- `--drive` — tanh saturation amount (default `0.8`; `0` disables).
- `--width` — stereo widening factor (default `1.12`; `1.0` leaves it alone).
- `--subtype` — output sample format, e.g. `PCM_16`, `PCM_24`, `FLOAT`
  (default `PCM_24` for WAV, else the format's libsndfile default).
- `--seed N` — reproducible per-run variation; omit it and every run is a
  slightly different flip (a few cents of detune and ~0.5% tempo wobble are
  applied so independent runs are never identical).

The defaults give a *noticeable* flip — down a whole step, a touch slower,
lightly filtered and saturated — that still reads as the same song. Push
`--semitones`/`--tempo` further for a heavier flip, or toward `0`/`1` for a
subtler one.

```bash
$ python flip.py track.mp3                       # default noticeable flip
wrote flipped audio to track.flip.wav            # lossless 24-bit WAV

$ python flip.py track.mp3 --semitones -5 --tempo 0.9 --lowpass 8000
wrote flipped audio to track.flip.wav            # heavier, darker flip
```

Formats depend on your libsndfile build (run `--list-formats`) — typically
**WAV, FLAC, OGG, AIFF, MP3**. **AAC/M4A need ffmpeg and are not handled
here.** Requires `soundfile` and `numpy` (`pip install -r requirements.txt`).

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
python test_flip.py            # needs soundfile + numpy (skips if missing)
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
staying near-inaudible, that the normal/high presets shift time alignment and
that the presets increase in strength (subtle < normal < high), that a
seed is reproducible while different seeds diverge, that each run yields a
unique file hash across every writable format, and that the output extension
is preserved.

`test_flip.py` confirms the phase-vocoder time-stretch changes length while
preserving pitch, that pitch-shift moves the pitch while preserving duration,
that the FFT filter attenuates the expected band, that saturation adds
harmonics and stays in range, that stereo widening scales the side channel
only, that a flip stays recognisable (length within ~10%, pitch shifted toward
the chosen key) yet seedable (same seed reproduces, different seeds diverge),
and that a file round-trip writes readable audio with the default name.

The WAV tools (`invert.py`, `uniquify.py`) use the standard library only.
`uniquify_audio.py` and `flip.py` additionally need `soundfile` and `numpy`
(`pip install -r requirements.txt`).
