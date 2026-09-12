# Local Prompt Studio

A prompt-based local interface for the CLI-Anything tools installed on this laptop.
All generated files are stored under `D:\CLI-Anything\PromptStudio`.

## Start

### Recommended: set it up once, never click anything again

Right-click `install-auto-start.ps1` and choose **Run with PowerShell**. One time only.

From then on the backend, ComfyUI, Ollama **and the web portal** all start
automatically after every Windows sign-in. A hidden watchdog rechecks them every
20 seconds and restarts anything that stopped, so the studio is simply always
there. Bookmark <http://localhost:3000> and open it like any other site.

To turn it off again, run `uninstall-auto-start.ps1`.

### Manual start

If auto-start is not installed, double-click `START_LOCAL_STUDIO.cmd`, or run:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-local-studio.ps1
```

The production portal opens at <http://localhost:3000>.

### If the portal does not come up

Check these logs under `D:\CLI-Anything\PromptStudio`:

| Log | Covers |
| --- | --- |
| `web-engine-error.log` | portal started by the watchdog |
| `web-error.log` | portal started manually |
| `api-error.log` | Python backend on `:8765` |
| `comfy-error.log` | ComfyUI on `:8188` |
| `ollama-error.log` | local LLM on `:11434` |
| `watchdog-error.log` | the watchdog itself |

## Available creation modes

| Mode | Local workflow | Typical time |
| --- | --- | --- |
| Image | Prompt → ComfyUI workflow → Z-Image Turbo on RTX GPU → PNG | 40–90 sec |
| Education Diagram | Prompt → separate ComfyUI stage visuals → deterministic FFmpeg labels/layout → PNG | 2–6 min |
| Audio | Prompt text → Microsoft Zira offline voice → Audacity CLI WAV → FFmpeg real MP3 | 10–30 sec |
| Video | Prompt + requested duration → ComfyUI visual + offline voice → exact-duration FFmpeg H.264/AAC render + editable Shotcut MLT | 1–10 min |
| PowerPoint | Prompt → local LLM slide content (Ollama) → LibreOffice Impress CLI → PPTX | 20–90 sec |
| Markdown | Prompt → local LLM document (Ollama) → MD | 5–40 sec |

If no local LLM is connected, PowerPoint and Markdown automatically fall back to
the older deterministic templates so they never fail.

## Offline behavior

The generation workflows above do not call cloud APIs. They work without internet
after the local models, applications, Python environment, and npm packages have
already been installed. ComfyUI must be running on `http://127.0.0.1:8188` for
image and video generation.

PowerPoint and Markdown use a local language model (Ollama) to write real content
from the prompt, and fall back to deterministic templates when Ollama is not
running. Audio reads the supplied text with the installed Microsoft Zira voice.
Image prompts use the installed Z-Image Turbo model.

Education Diagram mode has built-in accurate stage maps for butterfly life cycle,
water cycle, plant life cycle, and seven stages of life. Custom diagrams can use
`stages: idea, plan, build, test, launch`. Stage pictures are generated separately;
labels and ordering are rendered deterministically, so the model cannot omit or
duplicate a labelled stage. The subject art can still be stylized by the image model.

Video duration is read directly from prompts such as `for 10 seconds` or
`1.5 minute lesson`. It defaults to 30 seconds and is safety-limited to 120 seconds.

## Local AI text (Ollama)

PowerPoint and Markdown produce genuine, prompt-driven content when a local LLM is
available. This runs fully offline after a one-time model download.

1. Install Ollama (Windows): <https://ollama.com/download>
2. Pull a small, fast model once (needs internet only for this step):

   ```powershell
   ollama pull llama3.2:3b
   ```

3. That is all. `start-local-engines.ps1` starts `ollama serve` automatically when
   Ollama is installed, keeps model files under `D:\CLI-Anything\Ollama\models`,
   and the portal's "AI text engine" indicator turns green.

Change the model or host in `backend/config.json`:

```json
"llm": {
  "host": "http://127.0.0.1:11434",
  "model": "llama3.2:3b",
  "timeoutSeconds": 180
}
```

Any Ollama model works (e.g. `qwen2.5:3b`, `llama3.1:8b`). Larger models give
better slides and documents but are slower. With no model pulled, both modes keep
working via the offline templates.

## Important folders

- Portal source: `C:\Users\dvish\Documents\Codex\2026-09-03\https-github-com-hkuds-cli-anything\local-prompt-studio`
- Generated outputs: `D:\CLI-Anything\PromptStudio`
- Installed CLI commands: `D:\CLI-Anything\Python312\Scripts`
- Local applications/models: `D:\CLI-Anything\Apps` and the active ComfyUI model folders

## Local API

- `GET /api/status` — engine readiness, local LLM status (`llm`), and D-drive free space
- `GET /api/health` — fast backend health check
- `GET /api/jobs` — recent creations
- `POST /api/generate` — start a local job with `{ "type", "prompt" }`; type can be `image`, `diagram`, `audio`, `video`, `ppt`, or `markdown`
- `GET /api/jobs/{id}` — progress and result
- `GET /api/files/{id}` — open/download a completed output

The API listens only on `127.0.0.1:8765`.

## GitHub Pages frontend

The frontend can be hosted as a static GitHub Pages site while all generation continues on
this laptop. `.github/workflows/deploy-pages.yml` builds and deploys `dist/client` whenever
the `main` branch is pushed. The browser remembers the laptop API address, which defaults to
`http://localhost:8765`.
