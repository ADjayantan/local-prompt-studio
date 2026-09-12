# Local Prompt Studio — Master Prompt

Paste this whole file into a new AI session to give it full context on the project.
Everything below was verified against the running system on 2026-09-12.

---

## 1. What this project is

A **fully offline, prompt-to-content studio** running on one Windows 11 laptop with an
RTX GPU. You type a prompt in a local web portal, pick a mode, and it drives locally
installed engines to produce a real file on disk. No cloud APIs, no OpenAI/Anthropic
calls at generation time. The only internet ever needed was the one-time download of
the models and apps.

Six creation modes: **Image, Diagram, Audio, Video, PowerPoint, Markdown.**

| What | Where |
| --- | --- |
| Project root | `C:\Users\dvish\Documents\Codex\2026-09-03\https-github-com-hkuds-cli-anything\local-prompt-studio` |
| Generated output | `D:\CLI-Anything\PromptStudio\<Mode>\<jobid>_<slug>\` |
| Local apps | `D:\CLI-Anything\Apps\` (FFmpeg, LibreOffice, Audacity, Shotcut, Ollama, GIMP, Pandoc, SoX, 7-Zip) |
| ComfyUI | `D:\CLI-Anything\ComfyUI_windows_portable\ComfyUI` (models under `models\`) |
| Uploaded source images | `D:\CLI-Anything\PromptStudio\Uploads\<id>.png` |
| CLI wrappers | `D:\CLI-Anything\Python312\Scripts\cli-anything-*.exe` |
| Ollama models | `D:\CLI-Anything\Ollama\models` (kept off C: deliberately) |
| Portal | http://localhost:3000 |
| Backend API | http://127.0.0.1:8765 |
| Hosted frontend | https://adjayantan.github.io/local-prompt-studio/ |

Everything heavy lives on **D:** on purpose — C: is small.

---

## 2. Architecture

```
Browser (localhost:3000 or GitHub Pages)
        │  fetch /api/*  (CORS allowlisted)
        ▼
Python backend :8765  ── ThreadPoolExecutor(max_workers=2)
        │                 jobs persisted to D:\...\jobs.json
        ├── ComfyUI :8188      → images, diagram stage art, video key frame
        ├── Ollama  :11434     → slide text, markdown prose, diagram stage briefs
        ├── Windows SAPI TTS   → narration WAV
        ├── Audacity CLI       → audio project + WAV render
        ├── FFmpeg / FFprobe   → MP3 encode, video render, diagram assembly, verification
        ├── LibreOffice CLI    → PPTX + PDF
        └── Shotcut CLI        → editable .mlt project
```

### Frontend
- **React 19.2.6** + **Tailwind 4.2.1** + shadcn / `@base-ui/react`, icons via `lucide-react`
- Built with **vinext 1.0.0-beta.5** (`@openai/sites-vite-plugin`) on **Vite 8**
- Served in production by **wrangler 4.92** — `wrangler dev --config dist/server/wrangler.json --port 3000`
- `app/studio-client.tsx` (398 lines) is the entire UI: mode sidebar, prompt box, job
  progress, output preview, right-hand "Local system" status panel
- Polls `/api/status` every 5s, and `/api/jobs/{id}` every 1.5s while a job runs
- Lint/format via **oxlint / oxfmt** (not ESLint/Prettier)

### Backend
**Python 3.12 standard library only — no Flask/FastAPI/Django.**

- `backend/server.py` (288 lines) — `ThreadingHTTPServer` on `127.0.0.1:8765`
  - `ThreadPoolExecutor(max_workers=2)` — at most 2 generations run at once
  - Jobs persisted to `jobs.json`; writes go to a `.tmp` file then `Path.replace()`
    (atomic) under a `persist_lock`, with a separate `jobs_lock` for the in-memory dict.
    This pair of locks exists because two parallel jobs previously corrupted `jobs.json`.
  - CORS origins allowlisted in `backend/config.json`
- `backend/generators.py` (778 lines) — every pipeline plus `capability_status()`
- `backend/speak.ps1` — Windows offline TTS (Microsoft Zira voice, SAPI)
- `backend/config.json` — CORS allowlist + `llm` block (host/model/timeoutSeconds)
- `backend/tests/test_generators.py` — 17 tests, pure logic, **no network**, run with
  `python -m unittest discover -s backend/tests`

### API surface

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | fast liveness check |
| `GET /api/status` | engine readiness, `llm` block, D: free space |
| `GET /api/jobs` | recent jobs |
| `GET /api/jobs/{id}` | one job's progress/result |
| `POST /api/generate` | start a job — `{ "type", "prompt", "uploadId"?, "strength"? }` |
| `POST /api/uploads` | raw PNG/JPEG bytes (≤16 MB) → `{ "uploadId" }` for Image mode |
| `GET /api/files/{id}` | download/open the output |
| `GET /api/previews/{id}` | PDF preview (PowerPoint mode) |
| `POST /api/open-output` | open the D: output folder in Explorer |

`GET /` returns `{"error": "Not found"}` **by design** — 8765 is a JSON API, not a page.

---

## 3. The six pipelines

### Image — ComfyUI on the RTX GPU
Workflow JSON is generated per job and queued through `cli-anything-comfyui.exe`:
- `UNETLoader` → `z_image_turbo_bf16.safetensors` (Z-Image Turbo)
- `CLIPLoader` → `qwen_3_4b.safetensors`, type `lumina2`
- `VAELoader` → `ae.safetensors`
- `EmptySD3LatentImage` 1024×768 · `ModelSamplingAuraFlow` shift 3.0
- `KSampler` steps **8**, cfg **1.0**, `res_multistep` / `simple`, random seed
- ComfyUI **0.34.0**. Polls up to 5 min, then downloads the PNG.

The prompt is wrapped with a quality suffix and negative guidance ("no watermark, no
logo, no unreadable text, no duplicated objects").

**Final resolution is 2048×1536.** The GPU is an RTX 5050 Laptop with 8GB of VRAM, so
sampling a bigger latent is not an option. Instead every image finishes through
`UpscaleModelLoader` → `ImageUpscaleWithModel` (RealESRGAN_x4plus) → `ImageScale` back
down to 2×. Upscaling after the VAE decode costs far less VRAM than generating large,
and 4×-then-downsample is sharper than a straight 2×. `upscale_model_name()` queries
ComfyUI once and caches; with no upscaler installed the chain is skipped and the job
still produces a 1024×768 PNG.

**Image-to-image.** `POST /api/uploads` stores a PNG/JPEG and returns an id;
`POST /api/generate` accepts that id plus a `strength`. The file is pushed to ComfyUI's
input folder via its `/upload/image` endpoint, then `LoadImage` →
`ImageScaleToTotalPixels` (fits the upload to the sampling pixel budget, so a phone
photo cannot blow up the latent) → `VAEEncode` replaces the empty latent.

Three strengths, chosen by the user because keeping a photo and restyling it want
opposite settings:

| Strength | denoise | Behaviour |
| --- | --- | --- |
| `polish` | 0.35 | keeps the photo, cleans and sharpens it |
| `rework` | 0.65 | same composition, visible changes |
| `reimagine` | 0.92 | follows the prompt, keeps the layout |

Image-to-image also overrides **cfg to 2.5 and swaps `ConditioningZeroOut` for a real
text negative** — see the limitation note in §8 for why.

### Diagram — the accuracy-critical path
Multi-stage, because a single one-shot image reliably got life cycles wrong
(missing stages, duplicated adults).

1. **Resolve stages** — `diagram_stages(prompt)` in priority order:
   1. `preset_stages()` — hand-checked briefs for butterfly, water cycle, plant life
      cycle, seven stages of life. Instant and offline.
   2. `llm_stage_briefs()` — asks Ollama for `STAGE:` / `VISUAL:` pairs. **This is what
      the diagram's accuracy rests on**: the image model only ever sees a short phrase,
      so a bare word like "egg" made it draw a *chicken* egg. The LLM turns each stage
      into a concrete brief naming the organism, size, colour and surroundings.
   3. `education_stages()` — deterministic fallback so the diagram still renders with
      Ollama off.
2. **Generate each stage separately** through the image pipeline above.
3. **Assemble with FFmpeg** — `xstack` grid, `drawbox` + `drawtext` labels burned in.
   Labels come from code, never from the diffusion model, so they are always correct
   and correctly ordered. Heading font size auto-shrinks to fit the canvas.
4. **Verify** with ffprobe — codec `png` and exact expected dimensions.

A user can force stage names with `stages: a, b, c` in the prompt; those labels are
preserved exactly and only the visual briefs come from the model.

### Audio
`speak.ps1` (SAPI, Zira) → WAV → Audacity CLI project (`44100` Hz mono, track + clip,
render WAV) → **FFmpeg `libmp3lame` 192k** → ffprobe asserts `format=mp3` and
`codec=mp3`. The encode step exists because the file used to be a WAV merely *named*
`.mp3`.

### Video
Not true text-to-video. ComfyUI still + TTS narration → FFmpeg `zoompan`
(`min(zoom+0.0007,1.08)`) → **1920×1080, 30fps, libx264 `-tune stillimage` + AAC 192k**
→ a Shotcut `.mlt` project (`hd1080p30`) is also written so the clip is editable.
`parse_duration_seconds()` reads "10 sec" / "1.5 minutes" from the prompt (clamped to
120s); ffprobe asserts the result is within 0.35s of what was asked.

### PowerPoint
Ollama writes the slides → LibreOffice Impress CLI (`presentation_16_9`) builds the deck
→ exports **PPTX + a PDF preview**, both checked by magic bytes (`PK`, `%PDF-`).

**Important design note:** the model is asked for a flat plain-text format —
```
SLIDE: <title>
- <bullet>
```
not JSON. llama3.2:3b returns *malformed, recursively nested* JSON for a
`{"slides":[{"title","bullets"}]}` schema, which silently pushed every deck onto the
generic template. Plain text parses reliably. There is one retry, then a deterministic
template fallback.

### Markdown
Ollama writes prose directly; `_clean_markdown()` strips code fences and guarantees an
`H1`. No structured format needed, which is why this mode worked even while PPT was
silently falling back.

---

## 4. Local LLM

- **Ollama 0.34.0**, app at `D:\CLI-Anything\Apps\Ollama`, models at
  `D:\CLI-Anything\Ollama\models` (`OLLAMA_MODELS` is set permanently)
- **llama3.2:3b**, Q4_K_M, ~2.0 GB, 131072 context
- `llm_complete()` — single-shot `POST /api/generate`, `stream: false`, temp + `num_ctx`
  per caller, 180s timeout from config
- `ollama_status()` tolerates tag drift (`llama3.2:3b` vs `llama3.2:latest`) and falls
  back to the first installed model
- **Every LLM call has a non-LLM fallback.** No mode can fail because Ollama is down.

Swap the model in `backend/config.json`. `llama3.1:8b` gives better slides and better
stage briefs at the cost of speed.

---

## 5. Startup and persistence

| Script | Role |
| --- | --- |
| `start-local-engines.ps1` | starts backend + ComfyUI + Ollama + portal; `-Watch` runs a 20s watchdog loop guarded by a named mutex (`Local\PromptStudioEngineWatchdog`) |
| `start-local-studio.ps1` | manual start, waits for readiness, opens the browser |
| `install-auto-start.ps1` | writes HKCU Run entry `LocalPromptStudioEngines` |
| `uninstall-auto-start.ps1` | removes it |
| `INSTALL_AUTO_START.cmd` / `START_LOCAL_STUDIO.cmd` | double-click wrappers |

The watchdog restarts anything that dies within ~20s. Logs live in
`D:\CLI-Anything\PromptStudio\`: `api-*.log`, `comfy-*.log`, `ollama-*.log`,
`web-engine-*.log`, `watchdog-error.log`.

**Known issue:** the watchdog has been observed to exit silently, after which nothing
restarts the backend. If the API is down, check
`Get-CimInstance Win32_Process | Where CommandLine -like '*start-local-engines.ps1*'`
before debugging anything else.

Python `print()` from the backend is **buffered** when redirected to the log files, so
`api-start.log` can be 0 bytes even though the server is running and has logged. Do not
trust an empty log as evidence.

---

## 6. Deployment

`.github/workflows/deploy-pages.yml` builds the frontend with `npm run build:pages`
(`GITHUB_PAGES=true`) and publishes to GitHub Pages on every push to `main`.

The hosted page still talks to **your laptop** on `127.0.0.1:8765`. Chrome asks for
"Allow local network access" the first time. `https://adjayantan.github.io` is in the
backend's CORS allowlist. So: loading the page needs internet, generating does not.

---

## 7. Verified state (2026-09-12)

All six modes were run end-to-end and the output files inspected, not just the job status:

| Mode | Evidence |
| --- | --- |
| Image | valid 2048×1536 PNG through the upscaler, ~70s |
| Image-to-image | all three strengths run end to end; `polish` kept the source flower, `reimagine` applied the prompt |
| Diagram | 4 correct frog panels, labels and order exact, ~2m 40s |
| Audio | ffprobe `codec=mp3`, 44.1kHz mono |
| Video | asked 12s → **exactly 12.000000s**, h264 + aac, 1920×1080 |
| PowerPoint | real per-topic bullets + valid PDF preview, ~38s |
| Markdown | real subject content (chloroplasts, Calvin cycle) |

Backend tests: **17/17 pass.**

---

## 8. Honest limitations

1. **Video is not generative video** — one still image with a slow zoom plus narration.
2. **llama3.2:3b is small.** It misses edge instructions (asked for 8 planets in a
   5–7 slide deck, it stops at 7) and occasionally writes a biologically sloppy brief
   (gave an adult frog a "short stubby tail").
3. **Diffusion accuracy is not guaranteed.** The stage-brief fix removed the gross
   errors (chicken eggs, duplicate adults) but a tadpole can still come out looking
   fish-like. Only the burned-in labels are guaranteed correct.
7. **Image-to-image needs guidance that text-to-image does not.** Z-Image Turbo is
   distilled for cfg 1.0, and at cfg 1.0 there is no classifier-free guidance, so the
   input latent overwhelms the prompt. Asking to recolour a flower was measured
   returning the original colour on some seeds and a half-and-half blend on others,
   at denoise 0.55, 0.70 and 0.85 alike. Raising cfg to 2.5 *and* replacing
   `ConditioningZeroOut` with a real text negative made it consistent — a zeroed-out
   negative at cfg 2.5 was still not enough. Do not "simplify" either of those back.
4. **Only four curated diagram presets exist**; everything else depends on the LLM.
5. **Frontend lint is not clean** — accessibility and type warnings remain.
6. **Sign-out/sign-in auto-start has never actually been observed working**; only the
   registry entry has been confirmed present.

---

## 9. Working on this project

```powershell
# tests (fast, no network)
python -m unittest discover -s backend/tests

# after changing backend/generators.py or server.py — no hot reload
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*backend\server.py*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
# the watchdog restarts it in ~20s — confirm, do not assume

# after changing anything in app/
npm run build      # the portal serves dist/, not source

# health
curl http://127.0.0.1:8765/api/status
```

Conventions that matter:
- Backend stays **stdlib-only**. Do not add Flask/FastAPI.
- Every LLM path keeps a deterministic fallback.
- Every generated file is **verified** (ffprobe / magic bytes / dimensions) before the
  job is marked complete. Do not mark a job done on exit code alone.
- Ask the local model for **flat plain text**, never nested JSON.
- Outputs go to **D:**, never C:.
