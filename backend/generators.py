from __future__ import annotations

import json
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

Progress = Callable[[int, str], None]


def slugify(value: str, limit: int = 54) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_")
    return (value[:limit] or "creation").strip("_")


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
    directory = make_job_dir("audio", job_id, prompt)
    wav_path = _speak_to_wav(prompt, directory, progress)
    project = directory / "audio.audacity-cli.json"
    output = directory / f"{slugify(prompt)}.mp3"
    progress(50, "Creating Audacity project")
    run([AUDACITY, "project", "new", "--name", slugify(prompt), "--sample-rate", "44100", "--channels", "1", "--output", project])
    run([AUDACITY, "--project", project, "track", "add", "--name", "Narration", "--type", "audio"])
    run([AUDACITY, "--project", project, "clip", "add", "0", wav_path, "--name", "Offline narration"])
    progress(76, "Rendering MP3 with Audacity CLI")
    run([AUDACITY, "--project", project, "export", "render", output, "--preset", "mp3", "--overwrite"], timeout=180)
    if not output.exists() or output.stat().st_size < 1000:
        raise RuntimeError("Audacity CLI did not create a valid MP3")
    progress(100, "Audio ready")
    return output


def generate_video(job_id: str, prompt: str, progress: Progress) -> Path:
    require(SHOTCUT, "Shotcut CLI")
    require(FFMPEG, "FFmpeg")
    directory = make_job_dir("video", job_id, prompt)
    progress(4, "Creating key visual")
    key_visual = generate_image(f"{job_id}_visual", prompt, lambda pct, msg: progress(min(58, 4 + pct // 2), msg))
    narration = _speak_to_wav(prompt, directory, lambda pct, msg: progress(60 + pct // 10, msg))
    source = directory / "source.mp4"
    progress(68, "Building motion sequence with FFmpeg")
    run([
        FFMPEG, "-y", "-loop", "1", "-i", key_visual, "-i", narration,
        "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,zoompan=z='min(zoom+0.0007,1.08)':d=900:s=1920x1080:fps=30,format=yuv420p",
        "-c:v", "libx264", "-preset", "fast", "-tune", "stillimage", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-t", "30", source,
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
    duration = float(probe.get("format", {}).get("duration", 0)) if isinstance(probe, dict) else 0
    codecs = {stream.get("codec_name") for stream in probe.get("streams", [])} if isinstance(probe, dict) else set()
    if not output.exists() or output.stat().st_size < 10000 or duration < 1 or "h264" not in codecs:
        raise RuntimeError("Video verification failed: expected a playable H.264 MP4")
    progress(100, "Video ready")
    return output


def generate_ppt(job_id: str, prompt: str, progress: Progress) -> Path:
    require(LIBREOFFICE, "LibreOffice CLI")
    directory = make_job_dir("ppt", job_id, prompt)
    project = directory / "presentation.lo-cli.json"
    output = directory / f"{slugify(prompt)}.pptx"
    preview = output.with_suffix(".pdf")
    topic = prompt.strip().rstrip(".")
    slides = [
        (topic, "A locally generated presentation\nCreated with CLI-Anything + LibreOffice"),
        ("Overview", f"What {topic} means\nWhy this topic matters\nWhat this presentation covers"),
        ("Key ideas", f"Core concepts behind {topic}\nImportant terms and relationships\nA simple way to remember the topic"),
        ("How it works", f"Step-by-step view of {topic}\nInputs, process, and outcomes\nConnections between each stage"),
        ("Examples and applications", f"Real-world examples of {topic}\nWhere we see it in daily life\nPractical uses and observations"),
        ("Summary", f"Main lessons from {topic}\nQuestions for discussion\nThank you"),
    ]
    progress(12, "Creating LibreOffice Impress project")
    run([LIBREOFFICE, "document", "new", "--type", "impress", "--name", topic, "--profile", "presentation_16_9", "--output", project])
    for index, (title, content) in enumerate(slides):
        run([LIBREOFFICE, "--project", project, "impress", "add-slide", "--title", title, "--content", content])
        progress(18 + index * 10, f"Writing slide {index + 1} of {len(slides)}")
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


def generate_markdown(job_id: str, prompt: str, progress: Progress) -> Path:
    directory = make_job_dir("markdown", job_id, prompt)
    output = directory / f"{slugify(prompt)}.md"
    topic = prompt.strip().rstrip(".")
    progress(35, "Building local Markdown template")
    body = f"""# {topic}

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

---

Generated fully offline by Local Prompt Studio.
"""
    output.write_text(body, encoding="utf-8")
    progress(100, "Markdown ready")
    return output


GENERATORS = {
    "image": generate_image,
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
    usage = shutil.disk_usage(OUTPUT_ROOT.anchor)
    return {
        "offline": True,
        "outputRoot": str(OUTPUT_ROOT),
        "freeGb": round(usage.free / (1024**3), 1),
        "capabilities": {
            "image": {"ready": COMFY.exists() and comfy_online, "engine": "ComfyUI + RTX GPU"},
            "audio": {"ready": AUDACITY.exists() and SPEAK_SCRIPT.exists(), "engine": "Windows TTS + Audacity"},
            "video": {"ready": SHOTCUT.exists() and FFMPEG.exists() and comfy_online, "engine": "ComfyUI + FFmpeg + Shotcut"},
            "ppt": {"ready": LIBREOFFICE.exists(), "engine": "LibreOffice Impress"},
            "markdown": {"ready": True, "engine": "Local template"},
        },
    }
