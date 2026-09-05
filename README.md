# Local Prompt Studio

A prompt-based local interface for the CLI-Anything tools installed on this laptop.
All generated files are stored under `D:\CLI-Anything\PromptStudio`.

## Start

Double-click `START_LOCAL_STUDIO.cmd`, or run:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-local-studio.ps1
```

The production portal opens at <http://localhost:3000>.

Run `install-auto-start.ps1` once to keep the laptop backend and ComfyUI available after
every Windows sign-in. A hidden watchdog checks them every 20 seconds and restarts either
service if it stops.

## Available creation modes

| Mode | Local workflow | Typical time |
| --- | --- | --- |
| Image | Prompt → ComfyUI workflow → Z-Image Turbo on RTX GPU → PNG | 40–90 sec |
| Audio | Prompt text → Microsoft Zira offline voice → Audacity CLI → MP3 | 10–30 sec |
| Video | Prompt → ComfyUI visual + offline voice → FFmpeg H.264 render + editable Shotcut MLT | 3–10 min |
| PowerPoint | Prompt → six-slide structured template → LibreOffice Impress CLI → PPTX | 20–90 sec |
| Markdown | Prompt → structured local report template → MD | under 5 sec |

## Offline behavior

The generation workflows above do not call cloud APIs. They work without internet
after the local models, applications, Python environment, and npm packages have
already been installed. ComfyUI must be running on `http://127.0.0.1:8188` for
image and video generation.

PowerPoint and Markdown currently use deterministic structured templates because
no general-purpose local language model is connected. Audio reads the supplied
text with the installed Microsoft Zira voice. Image prompts use the installed
Z-Image Turbo model.

## Important folders

- Portal source: `C:\Users\dvish\Documents\Codex\2026-09-03\https-github-com-hkuds-cli-anything\local-prompt-studio`
- Generated outputs: `D:\CLI-Anything\PromptStudio`
- Installed CLI commands: `D:\CLI-Anything\Python312\Scripts`
- Local applications/models: `D:\CLI-Anything\Apps` and the active ComfyUI model folders

## Local API

- `GET /api/status` — engine readiness and D-drive free space
- `GET /api/health` — fast backend health check
- `GET /api/jobs` — recent creations
- `POST /api/generate` — start a local job with `{ "type", "prompt" }`
- `GET /api/jobs/{id}` — progress and result
- `GET /api/files/{id}` — open/download a completed output

The API listens only on `127.0.0.1:8765`.

## GitHub Pages frontend

The frontend can be hosted as a static GitHub Pages site while all generation continues on
this laptop. `.github/workflows/deploy-pages.yml` builds and deploys `dist/client` whenever
the `main` branch is pushed. The browser remembers the laptop API address, which defaults to
`http://127.0.0.1:8765`.
