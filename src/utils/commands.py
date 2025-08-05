import asyncio
import aiofiles
import subprocess  # only for synchronous helper further below
from pathlib import Path

from fastapi import HTTPException
from loguru import logger

from src.config import settings


async def _run(cmd: list[str], cwd: Path | None = None) -> None:
    logger.debug("Running command: {}", " ".join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )

    stdout, stderr = await proc.communicate()
    stderr_text = stderr.decode(errors="ignore")

    if proc.returncode != 0:
        # show just the first 30 lines so the log stays readable
        snippet = "\n".join(stderr_text.splitlines()[:30])
        logger.error("Command failed ({}):\n{}", proc.returncode, snippet)

        from datetime import datetime

        # … inside the if proc.returncode != 0 block …
        log_path = (
            settings.workspace_root / f"{datetime.utcnow().isoformat()}_{cmd[0]}.log"
        )
        log_path.write_text(stderr_text, encoding="utf-8")

        logger.error(
            "Command failed ({}). Full log saved to {}", proc.returncode, log_path
        )
        raise HTTPException(
            status_code=500,
            detail=f"Command {' '.join(cmd)} failed – see server logs",
        )


async def generate_pdf_from_latex(latex_code: str, job_id: str) -> Path:
    """
    Save LaTeX → compile twice with pdflatex → return resulting PDF path.
    """
    tex_path = settings.workspace_root / f"{job_id}.tex"
    pdf_path = settings.workspace_root / f"{job_id}.pdf"

    async with aiofiles.open(tex_path, "w", encoding="utf-8") as f:
        await f.write(latex_code)

    pdflatex = ["pdflatex", "-interaction=nonstopmode", tex_path.name]

    # two passes for refs/toc
    await _run(pdflatex, cwd=settings.workspace_root)
    await _run(pdflatex, cwd=settings.workspace_root)

    if not pdf_path.exists():
        raise HTTPException(status_code=500, detail="PDF build failed")

    # cleanup aux files
    for ext in (".aux", ".log", ".out", ".tex"):
        (settings.workspace_root / f"{job_id}{ext}").unlink(missing_ok=True)

    return pdf_path


async def convert_pdf_to_pngs(pdf_path: Path, job_id: str) -> list[str]:
    """
    Convert each page of `pdf_path` into a PNG slide file, store them under
    settings.pngs_dir/{job_id}/slide_{n}.png, and return the public URLs.

    - Uses `pdftoppm` to generate intermediate files named slide-1.png, slide-2.png, etc.
    - Renames them to slide_{n}.png to match the audio naming scheme.
    - Cleans up the original PDF.
    """
    # Prepare output directory for this job
    out_dir = settings.pngs_dir / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Run pdftoppm; produces slide-1.png, slide-2.png, ...
    prefix = out_dir / "slide"
    cmd = [settings.pdftoppm_path, "-png", str(pdf_path), str(prefix)]
    await _run(cmd)

    # Gather and rename
    raw_pngs = sorted(
        out_dir.glob("slide-*.png"), key=lambda p: int(p.stem.split("-", 1)[1])
    )
    urls: list[str] = []
    for raw in raw_pngs:
        idx = int(raw.stem.split("-", 1)[1])
        new_name = f"slide_{idx}.png"
        new_path = out_dir / new_name
        raw.rename(new_path)
        urls.append(f"/pngs/{job_id}/{new_name}")

    # Cleanup
    pdf_path.unlink(missing_ok=True)
    return urls


async def run_ffmpeg(cmd: list[str]) -> None:
    """
    Run an ffmpeg command in a thread to avoid blocking the event loop.
    """
    logger.debug("Running ffmpeg command: {}", " ".join(cmd))
    await asyncio.to_thread(subprocess.run, cmd, check=True)


async def run_ffmpeg_async(cmd: list[str]) -> None:
    """
    Spawn FFmpeg as a subprocess without blocking the event loop.
    """
    logger.debug("Running ffmpeg command: {}", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        msg = stderr.decode().strip()
        raise RuntimeError(f"FFmpeg failed ({proc.returncode}): {msg}")


def build_slide_clip_cmd(
    png: Path,
    audio: Path,
    clip: Path,
    offset: float = 0.5,  # seconds
    threads: int = 2,  # ffmpeg threads to use for this job
) -> list[str]:
    """
    Create an MP4 clip in which the slide is on screen immediately
    and the narration starts `offset` seconds later.
    """
    offset_ms = int(offset * 1000)  # adelay expects milliseconds
    return [
        "ffmpeg",
        "-y",
        # ── video (loop the still PNG) ───────────────────────────────────────────
        "-loop",
        "1",
        "-framerate",
        "1",  # one frame per second is enough
        "-i",
        str(png),
        # ── audio ───────────────────────────────────────────────────────────────
        "-i",
        str(audio),
        # ── filtering ───────────────────────────────────────────────────────────
        "-filter_complex",
        # scale video → even dims & browser-friendly format
        (
            "[0:v]scale=trunc(iw/2)*2:trunc(ih/2)*2,"
            "format=yuv420p[v];"
            # pad the audio with `offset` ms of silence
            f"[1:a]adelay={offset_ms}|{offset_ms}[a]"
        ),
        "-map",
        "[v]",
        "-map",
        "[a]",
        # ── encoding ────────────────────────────────────────────────────────────
        "-c:v",
        "libx264",
        "-r",
        "30",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",  # stop when (delayed) audio ends
        "-threads",
        str(threads),  # keep CPU usage in check
        str(clip),
    ]


def build_concat_cmd(
    list_file: Path,
    output: Path,
) -> list[str]:
    """
    Concatenate multiple slide clips into one MP4 with faststart for streaming.
    """
    return [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(output),
    ]
