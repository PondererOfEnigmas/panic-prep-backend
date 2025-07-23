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
    Use pdftoppm to convert each page to a PNG; return list of /pngs/... URLs.
    """
    out_prefix = settings.pngs_dir / f"{job_id}_slide"
    cmd = [settings.pdftoppm_path, "-png", str(pdf_path), str(out_prefix)]
    await _run(cmd)

    png_files = sorted(settings.pngs_dir.glob(f"{job_id}_slide*.png"))
    pdf_path.unlink(missing_ok=True)

    return [f"/pngs/{p.name}" for p in png_files]
    # urls = [f"/pngs/{p.name}" for p in png_files]
    # pdf_path.unlink(missing_ok=True)
    # return urls
