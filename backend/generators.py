from __future__ import annotations

import json
import math
import random
import re
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Callable


OUTPUT_ROOT = Path(r"D:\CLI-Anything\PromptStudio")
PYTHON_ROOT = Path(r"D:\CLI-Anything\Python312")
SCRIPTS = PYTHON_ROOT / "Scripts"
COMFY = SCRIPTS / "cli-anything-comfyui.exe"
LIBREOFFICE = SCRIPTS / "cli-anything-libreoffice.exe"
AUDACITY = SCRIPTS / "cli-anything-audacity.exe"
SHOTCUT = SCRIPTS / "cli-anything-shotcut.exe"
FFMPEG = Path(r"D:\CLI-Anything\Apps\FFmpeg\ffmpeg-9.0.1-full_build\bin\ffmpeg.exe")
FFPROBE = FFMPEG.with_name("ffprobe.exe")
SPEAK_SCRIPT = Path(__file__).with_name("speak.ps1")
CONFIG_FILE = Path(__file__).with_name("config.json")

# ---------------------------------------------------------------------------
# Local LLM (Ollama) — fully offline text generation.
# After you install Ollama and pull a model once, everything below runs with
# no internet. Host/model/timeout can be overridden in config.json -> "llm".
# ---------------------------------------------------------------------------
OLLAMA_HOST = "http://127.0.0.1:11434"
OLLAMA_MODEL = "llama3.2:3b"
OLLAMA_TIMEOUT = 180

Progress = Callable[[int, str], None]


def _load_llm_config() -> None:
    global OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_TIMEOUT
    try:
        config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    llm = config.get("llm") if isinstance(config, dict) else None
    if isinstance(llm, dict):
        OLLAMA_HOST = str(llm.get("host", OLLAMA_HOST)).rstrip("/")
        OLLAMA_MODEL = str(llm.get("model", OLLAMA_MODEL))
        try:
            OLLAMA_TIMEOUT = int(llm.get("timeoutSeconds", OLLAMA_TIMEOUT))
        except (TypeError, ValueError):
            pass


_load_llm_config()


def ollama_status() -> tuple[bool, str]:
    """Return (usable, model_name).

    usable is True only when the Ollama server is reachable AND a usable model
    is installed. Prefers the configured model, tolerates tag differences
    (llama3.2:3b vs llama3.2:latest), otherwise uses the first installed model.
    """
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=2) as response:
            if response.status != 200:
                return False, ""
            data = json.loads(response.read().decode("utf-8") or "{}")
    except Exception:
        return False, ""
    models = [str(item.get("name", "")) for item in data.get("models", []) if isinstance(item, dict)]
    models = [name for name in models if name]
    if OLLAMA_MODEL in models:
        return True, OLLAMA_MODEL
    base = OLLAMA_MODEL.split(":")[0]
    for name in models:
        if name.split(":")[0] == base:
            return True, name
    if models:
        return True, models[0]
    return False, ""


def llm_complete(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.4,
    num_ctx: int = 4096,
) -> str:
    """Single-shot completion from the local Ollama server. Raises if offline."""
    _usable, model = ollama_status()
    if not model:
        raise RuntimeError(
            f"Local LLM is not available. Install Ollama, then run: ollama pull {OLLAMA_MODEL}"
        )
    payload: dict = {
        "model": model,
        "prompt": user_prompt,
        "system": system_prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }
    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=OLLAMA_TIMEOUT) as response:
        data = json.loads(response.read().decode("utf-8") or "{}")
    text = str(data.get("response", "")).strip()
    if not text:
        raise RuntimeError("Local LLM returned an empty response")
    return text


def _clean_markdown(text: str, topic: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    if not text.lstrip().startswith("#"):
        text = f"# {topic}\n\n{text}"
    return text


def slugify(value: str, limit: int = 54) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_")
    return (value[:limit] or "creation").strip("_")


def parse_duration_seconds(prompt: str, default: float = 30.0, maximum: float = 120.0) -> float:
    """Read an explicit seconds/minutes duration from a prompt and clamp it safely."""
    match = re.search(r"\b(\d+(?:\.\d+)?)\s*(seconds?|secs?|sec|s)\b", prompt, re.IGNORECASE)
    multiplier = 1.0
    if not match:
        match = re.search(r"\b(\d+(?:\.\d+)?)\s*(minutes?|mins?|min|m)\b", prompt, re.IGNORECASE)
        multiplier = 60.0
    if not match:
        return default
    return max(1.0, min(float(match.group(1)) * multiplier, maximum))


STAGE_CLAUSE = re.compile(r"\b(?:stages?|steps?)\s*:\s*(.+)", re.IGNORECASE)


def explicit_stage_names(prompt: str) -> list[str]:
    """Read a user-supplied "stages: a, b, c" clause, if there is a usable one."""
    match = STAGE_CLAUSE.search(prompt)
    if not match:
        return []
    items = [part.strip(" .") for part in re.split(r",|->|→", match.group(1)) if part.strip(" .")]
    return items if 2 <= len(items) <= 8 else []


def diagram_subject(prompt: str) -> str:
    """The topic without its stage list, so a bare stage word never loses its subject."""
    return STAGE_CLAUSE.sub("", prompt).strip(" .,:-") or prompt.strip()


def diagram_title(prompt: str, limit: int = 60) -> str:
    """Drop the stage list from the heading — the labels under each panel already say it."""
    text = re.sub(r"[^A-Za-z0-9 -]", " ", diagram_subject(prompt))
    return " ".join(text.split()).upper()[:limit] or "EDUCATION DIAGRAM"


def preset_stages(prompt: str) -> list[tuple[str, str]]:
    """Hand-checked stage art briefs for the topics classrooms ask for most."""
    topic = prompt.lower()
    if "butterfly" in topic:
        return [
            ("EGG", "tiny monarch butterfly eggs attached beneath a milkweed leaf"),
            ("CATERPILLAR", "scientifically accurate striped monarch caterpillar eating a milkweed leaf"),
            ("CHRYSALIS", "single green monarch chrysalis hanging from a twig"),
            ("BUTTERFLY", "single adult monarch butterfly with anatomically accurate wings"),
        ]
    if "water cycle" in topic:
        return [
            ("EVAPORATION", "sun warming a lake while clean water vapor rises"),
            ("CONDENSATION", "water vapor cooling and forming clouds"),
            ("PRECIPITATION", "rain falling from clouds over mountains"),
            ("COLLECTION", "rainwater collecting in rivers lakes and groundwater"),
        ]
    if "plant" in topic and ("life cycle" in topic or "lifecycle" in topic):
        return [
            ("SEED", "single healthy seed in moist soil"),
            ("GERMINATION", "seed germinating with first root and shoot"),
            ("SEEDLING", "young green seedling with first leaves"),
            ("MATURE PLANT", "mature flowering plant producing new seeds"),
        ]
    if "seven stages" in topic or "7 stages" in topic:
        return [
            ("INFANT", "newborn infant safely resting"),
            ("SCHOOLCHILD", "school age child carrying books"),
            ("TEENAGER", "healthy teenager learning and socializing"),
            ("YOUNG ADULT", "young adult beginning work and relationships"),
            ("MIDDLE AGE", "confident middle aged adult with family and career"),
            ("OLDER ADULT", "active healthy older adult"),
            ("LATE LIFE", "very old adult supported with dignity and care"),
        ]
    return []


def education_stages(prompt: str) -> list[tuple[str, str]]:
    """Resolve stages without the local model — presets, then an explicit list, then a
    last-resort generic outline."""
    preset = preset_stages(prompt)
    if preset:
        return preset

    explicit = explicit_stage_names(prompt)
    if explicit:
        subject = diagram_subject(prompt)
        return [(item.upper()[:28], f"the {item} stage of {subject}") for item in explicit]
    return [
        ("BEGINNING", f"the beginning stage of {prompt}"),
        ("DEVELOPMENT", f"the development stage of {prompt}"),
        ("TRANSITION", f"the transition stage of {prompt}"),
        ("COMPLETION", f"the completed stage of {prompt}"),
    ]


def _parse_stage_briefs(raw: str) -> list[tuple[str, str]]:
    """Read the model's STAGE:/VISUAL: pairs."""
    stages: list[tuple[str, str]] = []
    label = ""
    for line in raw.splitlines():
        line = line.strip().lstrip("-•*").strip()
        stage_match = re.match(r"^STAGE\s*[:\-]\s*(.+)$", line, re.IGNORECASE)
        if stage_match:
            label = re.sub(r"[^A-Za-z0-9 -]", "", stage_match.group(1)).strip()[:28]
            continue
        visual_match = re.match(r"^VISUAL\s*[:\-]\s*(.+)$", line, re.IGNORECASE)
        if visual_match and label:
            stages.append((label.upper(), visual_match.group(1).strip()))
            label = ""
    return stages[:8]


def llm_stage_briefs(subject: str, labels: list[str] | None = None) -> list[tuple[str, str]]:
    """Ask the local model what each stage actually looks like.

    The image model only ever sees a short phrase, so a bare stage word like "egg"
    makes it draw a chicken egg. This turns each stage into a concrete brief that
    names the organism, which is what the diagram accuracy depends on.
    """
    if labels:
        instruction = (
            "Write one visual brief for each of these stages, in exactly this order: "
            + ", ".join(labels)
            + ".\nKeep these stage labels exactly as given.\n"
        )
    else:
        instruction = "List its real stages in correct order — 3 to 6 of them.\n"
    system_prompt = (
        "You are a science teacher briefing a classroom illustrator. You state exactly "
        "what each stage physically looks like, in plain text only."
    )
    user_prompt = (
        f'Topic: "{subject}".\n'
        + instruction
        + "Respond using EXACTLY this format and nothing else:\n"
        "STAGE: <short label, 1 to 3 words>\n"
        "VISUAL: <one sentence describing what this stage looks like>\n"
        "Repeat that pair for every stage. Each VISUAL sentence must name the organism "
        "or object concretely and describe its size, colour and surroundings, so an "
        "illustrator cannot confuse it with a different species or object. Never write "
        "a bare word. No commentary, no markdown, no numbering."
    )
    stages = _parse_stage_briefs(llm_complete(system_prompt, user_prompt, temperature=0.3))
    if labels:
        if len(stages) < len(labels):
            raise RuntimeError("Local LLM skipped one of the requested stages")
        return [(label.upper()[:28], visual) for label, (_parsed, visual) in zip(labels, stages)]
    if len(stages) < 3:
        raise RuntimeError("Local LLM did not return enough usable stages")
    return stages


def diagram_stages(prompt: str) -> list[tuple[str, str]]:
    """Best available stage briefs: curated presets, then the local model, then the
    deterministic fallback."""
    preset = preset_stages(prompt)
    if preset:
        return preset
    subject = diagram_subject(prompt)
    explicit = explicit_stage_names(prompt)
    try:
        return llm_stage_briefs(subject, explicit or None)
    except Exception as exc:  # noqa: BLE001 - the diagram must still render offline
        print(f"[diagram] Local LLM stage research failed, using fallback: {exc}")
        return education_stages(prompt)


def run(command: list[str | Path], timeout: int = 300, json_output: bool = False) -> dict | list | str:
    args = [str(part) for part in command]
    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}"
        raise RuntimeError(f"{Path(args[0]).name}: {detail}")
    output = completed.stdout.strip()
    if json_output:
        return json.loads(output or "{}")
    return output


def require(path: Path, label: str) -> None:
    if not path.exists():
        raise RuntimeError(f"{label} is not installed at {path}")


def make_job_dir(kind: str, job_id: str, prompt: str) -> Path:
    directory = OUTPUT_ROOT / kind.capitalize() / f"{job_id}_{slugify(prompt)}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def generate_image(job_id: str, prompt: str, progress: Progress) -> Path:
    require(COMFY, "ComfyUI CLI")
    directory = make_job_dir("image", job_id, prompt)
    workflow_path = directory / "workflow.json"
    refined_prompt = (
        f"{prompt}. High quality original visual, clear composition, rich natural detail, "
        "professional lighting, polished educational editorial style. No watermark, no logo, "
        "no unreadable text, no duplicated objects."
    )
    workflow = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "z_image_turbo_bf16.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_4b.safetensors", "type": "lumina2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": refined_prompt}},
        "5": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}},
        "6": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 1024, "height": 768, "batch_size": 1}},
        "7": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.0}},
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["7", 0], "positive": ["4", 0], "negative": ["5", 0],
                "latent_image": ["6", 0], "seed": random.randint(1, 2**31 - 1),
                "steps": 8, "cfg": 1.0, "sampler_name": "res_multistep",
                "scheduler": "simple", "denoise": 1.0,
            },
        },
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": f"PromptStudio/{job_id}/render"}},
    }
    workflow_path.write_text(json.dumps(workflow, indent=2), encoding="utf-8")
    progress(8, "Validating ComfyUI workflow")
    run([COMFY, "workflow", "validate", str(workflow_path)], timeout=30)
    progress(14, "Queued on RTX GPU")
    queued = run([COMFY, "--json", "queue", "prompt", "--workflow", str(workflow_path)], timeout=30, json_output=True)
    if not isinstance(queued, dict) or not queued.get("prompt_id"):
        raise RuntimeError(f"ComfyUI returned no prompt id: {queued}")
    prompt_id = str(queued["prompt_id"])

    for attempt in range(150):
        time.sleep(2)
        try:
            listed = run([COMFY, "--json", "images", "list", "--prompt-id", prompt_id], timeout=20, json_output=True)
            if isinstance(listed, list) and listed:
                break
            if isinstance(listed, dict) and (listed.get("images") or listed.get("outputs")):
                break
        except (RuntimeError, json.JSONDecodeError):
            pass
        progress(min(86, 18 + attempt), "Generating image locally")
    else:
        raise RuntimeError("ComfyUI generation timed out after 5 minutes")

    progress(90, "Downloading generated image")
    run([COMFY, "images", "download-all", "--prompt-id", prompt_id, "--output-dir", str(directory), "--overwrite"], timeout=60)
    images = sorted(directory.glob("*.png"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not images or images[0].stat().st_size < 1024:
        raise RuntimeError("ComfyUI finished but no valid PNG was downloaded")
    final_path = directory / f"{slugify(prompt)}.png"
    if images[0] != final_path:
        shutil.copy2(images[0], final_path)
    progress(100, "Image ready")
    return final_path


def generate_diagram(job_id: str, prompt: str, progress: Progress) -> Path:
    """Generate stage art separately, then assemble truthful labels with FFmpeg."""
    require(COMFY, "ComfyUI CLI")
    require(FFMPEG, "FFmpeg")
    require(FFPROBE, "FFprobe")
    stages = diagram_stages(prompt)
    directory = make_job_dir("diagram", job_id, prompt)
    stage_images: list[Path] = []
    generation_span = 76 / len(stages)
    for index, (label, subject) in enumerate(stages):
        stage_prompt = (
            f"One isolated stage illustration for an accurate classroom diagram: {subject}. "
            "Show only this subject, centered, clean pale background, scientifically plausible, "
            "no words, no letters, no labels, no extra stages, no duplicate subject"
        )
        start = 4 + index * generation_span
        image = generate_image(
            f"{job_id}_stage_{index + 1}",
            stage_prompt,
            lambda pct, msg, start=start, index=index: progress(
                min(80, round(start + pct * generation_span / 100)),
                f"Stage {index + 1}/{len(stages)}: {msg}",
            ),
        )
        stage_images.append(image)

    progress(84, "Assembling fixed labels and stage order")
    cell_width, cell_height = 512, 384
    columns = 2 if len(stages) == 4 else min(4, len(stages))
    rows = math.ceil(len(stages) / columns)
    width, grid_height = columns * cell_width, rows * cell_height
    height = grid_height + 72
    font = "C\\:/Windows/Fonts/arialbd.ttf"
    filters: list[str] = []
    labelled_streams: list[str] = []
    layouts: list[str] = []
    for index, ((label, _subject), _image) in enumerate(zip(stages, stage_images)):
        safe_label = re.sub(r"[^A-Za-z0-9 -]", "", label).strip()[:28]
        filters.append(
            f"[{index}:v]scale={cell_width}:{cell_height}:force_original_aspect_ratio=increase,"
            f"crop={cell_width}:{cell_height},drawbox=x=0:y=ih-58:w=iw:h=58:color=black@0.72:t=fill,"
            f"drawtext=fontfile='{font}':text='{index + 1}. {safe_label}':fontcolor=white:fontsize=28:"
            f"x=(w-text_w)/2:y=h-text_h-14[v{index}]"
        )
        labelled_streams.append(f"[v{index}]")
        layouts.append(f"{index % columns * cell_width}_{index // columns * cell_height}")
    filters.append(
        f"{''.join(labelled_streams)}xstack=inputs={len(stages)}:layout={'|'.join(layouts)}:fill=white[grid]"
    )
    safe_title = diagram_title(prompt)
    # Arial Bold runs about 0.62 em per character; shrink until the heading fits the canvas.
    title_size = max(16, min(36, int((width - 48) / (0.62 * len(safe_title)))))
    filters.append(
        f"[grid]pad={width}:{height}:0:72:color=white,"
        f"drawtext=fontfile='{font}':text='{safe_title}':fontcolor=black:fontsize={title_size}:"
        f"x=(w-text_w)/2:y=(72-text_h)/2[out]"
    )
    output = directory / f"{slugify(prompt)}_accurate_diagram.png"
    command: list[str | Path] = [FFMPEG, "-y"]
    for image in stage_images:
        command.extend(["-i", image])
    command.extend(["-filter_complex", ";".join(filters), "-map", "[out]", "-frames:v", "1", output])
    run(command, timeout=300)
    probe = run([
        FFPROBE, "-v", "error", "-show_entries", "stream=codec_name,width,height", "-of", "json", output,
    ], timeout=30, json_output=True)
    streams = probe.get("streams", []) if isinstance(probe, dict) else []
    valid = bool(streams) and streams[0].get("codec_name") == "png" and streams[0].get("width") == width and streams[0].get("height") == height
    if not output.exists() or output.stat().st_size < 5000 or not valid:
        raise RuntimeError("Education diagram verification failed: expected a labelled PNG grid")
    progress(100, "Accurate education diagram ready")
    return output


def _speak_to_wav(text: str, directory: Path, progress: Progress) -> Path:
    text_file = directory / "speech.txt"
    wav_path = directory / "speech_raw.wav"
    text_file.write_text(text, encoding="utf-8-sig")
    progress(28, "Speaking with Microsoft Zira")
    run([
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", SPEAK_SCRIPT,
        "-TextFile", text_file, "-OutputFile", wav_path,
    ], timeout=180)
    if not wav_path.exists() or wav_path.stat().st_size < 1000:
        raise RuntimeError("Windows offline speech did not create a valid WAV")
    return wav_path


def generate_audio(job_id: str, prompt: str, progress: Progress) -> Path:
    require(AUDACITY, "Audacity CLI")
    require(FFMPEG, "FFmpeg")
    require(FFPROBE, "FFprobe")
    directory = make_job_dir("audio", job_id, prompt)
    wav_path = _speak_to_wav(prompt, directory, progress)
    project = directory / "audio.audacity-cli.json"
    rendered_wav = directory / "audacity_render.wav"
    output = directory / f"{slugify(prompt)}.mp3"
    progress(50, "Creating Audacity project")
    run([AUDACITY, "project", "new", "--name", slugify(prompt), "--sample-rate", "44100", "--channels", "1", "--output", project])
    run([AUDACITY, "--project", project, "track", "add", "--name", "Narration", "--type", "audio"])
    run([AUDACITY, "--project", project, "clip", "add", "0", wav_path, "--name", "Offline narration"])
    progress(72, "Rendering WAV with Audacity CLI")
    run([AUDACITY, "--project", project, "export", "render", rendered_wav, "--preset", "wav", "--overwrite"], timeout=180)
    progress(88, "Encoding real MP3 with FFmpeg")
    run([FFMPEG, "-y", "-i", rendered_wav, "-codec:a", "libmp3lame", "-b:a", "192k", output], timeout=180)
    probe = run([
        FFPROBE, "-v", "error", "-show_entries", "format=format_name,duration,size:stream=codec_name",
        "-of", "json", output,
    ], timeout=30, json_output=True)
    format_name = str(probe.get("format", {}).get("format_name", "")) if isinstance(probe, dict) else ""
    codecs = {stream.get("codec_name") for stream in probe.get("streams", [])} if isinstance(probe, dict) else set()
    if not output.exists() or output.stat().st_size < 1000 or "mp3" not in format_name or "mp3" not in codecs:
        raise RuntimeError("Audio verification failed: expected a real MP3 container and codec")
    progress(100, "Audio ready")
    return output


def generate_video(job_id: str, prompt: str, progress: Progress) -> Path:
    require(SHOTCUT, "Shotcut CLI")
    require(FFMPEG, "FFmpeg")
    directory = make_job_dir("video", job_id, prompt)
    requested_duration = parse_duration_seconds(prompt)
    frame_count = max(30, round(requested_duration * 30))
    progress(4, "Creating key visual")
    key_visual = generate_image(f"{job_id}_visual", prompt, lambda pct, msg: progress(min(58, 4 + pct // 2), msg))
    narration = _speak_to_wav(prompt, directory, lambda pct, msg: progress(60 + pct // 10, msg))
    source = directory / "source.mp4"
    progress(68, "Building motion sequence with FFmpeg")
    run([
        FFMPEG, "-y", "-loop", "1", "-i", key_visual, "-i", narration,
        "-filter_complex",
        f"[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
        f"zoompan=z='min(zoom+0.0007,1.08)':d={frame_count}:s=1920x1080:fps=30,format=yuv420p[v];"
        f"[1:a]apad=whole_dur={requested_duration}[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-tune", "stillimage", "-c:a", "aac", "-b:a", "192k",
        "-t", str(requested_duration), source,
    ], timeout=600)
    if not source.exists() or source.stat().st_size < 10000:
        raise RuntimeError("FFmpeg did not create a valid source video")

    project = directory / "video.mlt"
    output = directory / f"{slugify(prompt)}.mp4"
    progress(82, "Creating Shotcut timeline")
    run([SHOTCUT, "project", "new", "--profile", "hd1080p30", "--output", project])
    imported = run([SHOTCUT, "--json", "--project", project, "media", "import", source], json_output=True)
    clip_id = imported.get("clip_id") if isinstance(imported, dict) else None
    if not clip_id:
        raise RuntimeError(f"Shotcut CLI returned no clip id: {imported}")
    run([SHOTCUT, "--project", project, "timeline", "add-track", "--type", "video", "--name", "Prompt video"])
    run([SHOTCUT, "--project", project, "timeline", "add-clip", str(clip_id), "--track", "0"])
    progress(90, "Saving editable Shotcut project")
    # The installed Shotcut harness currently exports a one-frame file for this
    # generated still-image timeline. Keep the real MLT project for editing, and
    # use the verified FFmpeg render as the final delivery file.
    shutil.copy2(source, output)
    probe = run([
        FFPROBE, "-v", "error", "-show_entries", "format=duration,size:stream=codec_name,width,height",
        "-of", "json", output,
    ], timeout=30, json_output=True)
    actual_duration = float(probe.get("format", {}).get("duration", 0)) if isinstance(probe, dict) else 0
    codecs = {stream.get("codec_name") for stream in probe.get("streams", [])} if isinstance(probe, dict) else set()
    if not output.exists() or output.stat().st_size < 10000 or abs(requested_duration - actual_duration) > 0.35 or "h264" not in codecs or "aac" not in codecs:
        raise RuntimeError(f"Video verification failed: expected a playable {requested_duration:g}-second H.264/AAC MP4")
    progress(100, "Video ready")
    return output


def _ppt_template_slides(topic: str) -> list[tuple[str, str]]:
    """Deterministic offline fallback used when no local LLM is available."""
    return [
        (topic, "A locally generated presentation\nCreated with CLI-Anything + LibreOffice"),
        ("Overview", f"What {topic} means\nWhy this topic matters\nWhat this presentation covers"),
        ("Key ideas", f"Core concepts behind {topic}\nImportant terms and relationships\nA simple way to remember the topic"),
        ("How it works", f"Step-by-step view of {topic}\nInputs, process, and outcomes\nConnections between each stage"),
        ("Examples and applications", f"Real-world examples of {topic}\nWhere we see it in daily life\nPractical uses and observations"),
        ("Summary", f"Main lessons from {topic}\nQuestions for discussion\nThank you"),
    ]


def _parse_slides_text(raw: str) -> list[tuple[str, str]]:
    """Parse the small model's plain-text slide format (far more reliable than
    asking a 3B model for nested JSON, which it frequently mangles)."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\s*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw).strip()
    slides: list[tuple[str, str]] = []
    title: str | None = None
    bullets: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^SLIDE\s*[:\-]\s*(.+)$", line, re.IGNORECASE)
        if match:
            if title or bullets:
                slides.append((title or "Slide", "\n".join(bullets)))
            title = match.group(1).strip().strip("*").strip()
            bullets = []
            continue
        bullet = re.sub(r"^[-•*]\s*|^\d+[.)]\s*", "", line).strip()
        if bullet:
            bullets.append(bullet)
    if title or bullets:
        slides.append((title or "Slide", "\n".join(bullets)))
    return slides[:8]


def _ppt_llm_slides(topic: str) -> list[tuple[str, str]]:
    system_prompt = (
        "You are a presentation designer. You produce clear, accurate, classroom-ready "
        "slide content in plain text only — never JSON, never markdown."
    )
    user_prompt = (
        f'Create slide content about: "{topic}".\n'
        "Respond using EXACTLY this plain-text format and nothing else:\n"
        "SLIDE: <title>\n"
        "- <bullet>\n"
        "SLIDE: <title>\n"
        "- <bullet>\n"
        "- <bullet>\n"
        "Rules: 5 to 7 slides total. The first slide is a title slide with one bullet "
        "as a subtitle. Every other slide has 3 to 5 short bullets, each under about "
        "12 words. No numbering, no markdown, no commentary before or after."
    )
    for _ in range(2):
        response = llm_complete(system_prompt, user_prompt, temperature=0.4)
        slides = _parse_slides_text(response)
        if len(slides) >= 3:
            return slides
    raise RuntimeError("Local LLM did not return enough usable slides")


def generate_ppt(job_id: str, prompt: str, progress: Progress) -> Path:
    require(LIBREOFFICE, "LibreOffice CLI")
    directory = make_job_dir("ppt", job_id, prompt)
    project = directory / "presentation.lo-cli.json"
    output = directory / f"{slugify(prompt)}.pptx"
    preview = output.with_suffix(".pdf")
    topic = prompt.strip().rstrip(".")

    slides: list[tuple[str, str]] | None = None
    usable, _model = ollama_status()
    if usable:
        progress(8, "Writing slide content with local AI")
        try:
            slides = _ppt_llm_slides(topic)
        except Exception as exc:  # noqa: BLE001 - degrade gracefully to template
            print(f"[ppt] Local LLM generation failed, using template: {exc}")
            slides = None
    if not slides:
        slides = _ppt_template_slides(topic)

    progress(12, "Creating LibreOffice Impress project")
    run([LIBREOFFICE, "document", "new", "--type", "impress", "--name", topic, "--profile", "presentation_16_9", "--output", project])
    for index, (title, content) in enumerate(slides):
        run([LIBREOFFICE, "--project", project, "impress", "add-slide", "--title", title, "--content", content])
        progress(min(80, 18 + index * 9), f"Writing slide {index + 1} of {len(slides)}")
    progress(84, "Rendering PPTX with LibreOffice")
    run([LIBREOFFICE, "--project", project, "export", "render", output, "--preset", "pptx", "--overwrite"], timeout=300)
    if not output.exists() or output.stat().st_size < 1000 or output.read_bytes()[:2] != b"PK":
        raise RuntimeError("LibreOffice CLI did not create a valid PPTX")
    progress(94, "Creating browser preview")
    run([LIBREOFFICE, "--project", project, "export", "render", preview, "--preset", "pdf", "--overwrite"], timeout=300)
    if not preview.exists() or preview.stat().st_size < 1000 or preview.read_bytes()[:5] != b"%PDF-":
        raise RuntimeError("LibreOffice CLI did not create a valid PDF preview")
    progress(100, "PowerPoint ready")
    return output


def _markdown_template(topic: str) -> str:
    """Deterministic offline fallback used when no local LLM is available."""
    return f"""# {topic}

## Overview

This document is a structured offline starting point for **{topic}**.

## Objectives

- Define the topic clearly.
- Identify its most important ideas.
- Record examples, observations, and practical actions.

## Key ideas

1. Background and context
2. Main concepts and relationships
3. Real-world examples
4. Practical applications

## Notes

- Add your research or classroom notes here.
- Replace this line with facts, examples, or references already available locally.

## Summary

{topic} can be understood by connecting its purpose, core ideas, and real-world applications.
"""


def generate_markdown(job_id: str, prompt: str, progress: Progress) -> Path:
    directory = make_job_dir("markdown", job_id, prompt)
    output = directory / f"{slugify(prompt)}.md"
    topic = prompt.strip().rstrip(".")

    body: str | None = None
    usable, _model = ollama_status()
    if usable:
        progress(25, "Writing document with local AI")
        try:
            system_prompt = (
                "You are a precise technical writer. Write a well-structured, accurate Markdown "
                "document. Use headings, short paragraphs, and bullet lists where useful. Do not "
                "wrap the whole document in a code fence."
            )
            user_prompt = (
                f'Write a complete Markdown document for this request: "{prompt}".\n'
                f'Start with a level-1 heading titled "{topic}". Include an overview, several '
                "sections with real explanatory content, and a short summary at the end."
            )
            body = _clean_markdown(
                llm_complete(system_prompt, user_prompt, temperature=0.5, num_ctx=8192),
                topic,
            )
        except Exception as exc:  # noqa: BLE001 - degrade gracefully to template
            print(f"[markdown] Local LLM generation failed, using template: {exc}")
            body = None
    if not body:
        progress(35, "Building local Markdown template")
        body = _markdown_template(topic)

    body = body.rstrip() + "\n\n---\n\n_Generated fully offline by Local Prompt Studio._\n"
    output.write_text(body, encoding="utf-8")
    progress(100, "Markdown ready")
    return output


GENERATORS = {
    "image": generate_image,
    "diagram": generate_diagram,
    "audio": generate_audio,
    "video": generate_video,
    "ppt": generate_ppt,
    "markdown": generate_markdown,
}


def generate(kind: str, job_id: str, prompt: str, progress: Progress) -> Path:
    if kind not in GENERATORS:
        raise ValueError(f"Unsupported creation type: {kind}")
    clean_prompt = prompt.strip()
    if len(clean_prompt) < 3:
        raise ValueError("Prompt must contain at least 3 characters")
    if len(clean_prompt) > 4000:
        raise ValueError("Prompt is too long; maximum is 4000 characters")
    return GENERATORS[kind](job_id, clean_prompt, progress)


def capability_status() -> dict:
    comfy_online = False
    try:
        with urllib.request.urlopen("http://127.0.0.1:8188/system_stats", timeout=2) as response:
            comfy_online = response.status == 200
    except Exception:
        pass
    llm_ready, llm_model = ollama_status()
    ppt_engine = "LibreOffice Impress + local AI" if llm_ready else "LibreOffice Impress (template)"
    markdown_engine = "Local AI writer" if llm_ready else "Local template"
    usage = shutil.disk_usage(OUTPUT_ROOT.anchor)
    return {
        "offline": True,
        "outputRoot": str(OUTPUT_ROOT),
        "freeGb": round(usage.free / (1024**3), 1),
        "llm": {"ready": llm_ready, "engine": "Ollama", "model": llm_model, "host": OLLAMA_HOST},
        "capabilities": {
            "image": {"ready": COMFY.exists() and comfy_online, "engine": "ComfyUI + RTX GPU"},
            "diagram": {"ready": COMFY.exists() and FFMPEG.exists() and comfy_online, "engine": "ComfyUI stages + FFmpeg layout"},
            "audio": {"ready": AUDACITY.exists() and FFMPEG.exists() and SPEAK_SCRIPT.exists(), "engine": "Windows TTS + Audacity + FFmpeg MP3"},
            "video": {"ready": SHOTCUT.exists() and FFMPEG.exists() and comfy_online, "engine": "ComfyUI + FFmpeg + Shotcut"},
            "ppt": {"ready": LIBREOFFICE.exists(), "engine": ppt_engine},
            "markdown": {"ready": True, "engine": markdown_engine},
        },
    }
