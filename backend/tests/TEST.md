# Local Prompt Studio Generator Test Plan

## Test inventory

- `test_generators.py`: 8 focused unit tests planned.
- Live API smoke tests: audio, exact-duration video, and education diagram.

## Unit test plan

- Duration parsing: seconds, minutes, default value, and safety clamp.
- Education stages: butterfly, water cycle, seven stages of life, and generic explicit stage lists.

## End-to-end plan

- Audio: generate through the installed Audacity CLI and FFmpeg, then require an MP3 container and MP3 codec with `ffprobe`.
- Video: request a short duration, render through ComfyUI/FFmpeg/Shotcut, then verify H.264 video, AAC audio, 1920x1080 dimensions, and requested duration tolerance.
- Education diagram: generate separate stage images through ComfyUI, assemble the labelled grid through FFmpeg, and verify a non-empty PNG with expected dimensions.

## Realistic workflows

- **Offline narration**: prompt to playable, correctly encoded MP3.
- **Timed promo**: prompt containing an explicit duration to an MP4 of that exact duration.
- **Classroom lifecycle diagram**: topic prompt to deterministic, labelled stage layout without relying on cloud AI.

Test results are appended only after all relevant checks pass.

## Test results

Last run: 2026-09-12

```text
Ran 8 tests in 0.001s
OK

Audio live API job: complete
ffprobe: codec_name=mp3, format_name=mp3, sample_rate=44100

Exact-duration video: complete
ffprobe: codec_name=h264 + aac, 1920x1080, duration=7.000000

Butterfly education diagram: complete
ffprobe: codec_name=png, 1024x840, size=728578 bytes

Frontend static production build: PASS (2 routes prerendered)
Python py_compile: PASS
```

**Summary:** 8/8 focused unit tests passed. All three real output workflows passed
format-level verification against installed local backends. Scientific subject art
remains diffusion-model output and should be visually reviewed; labels, stage count,
and stage order are deterministic.
