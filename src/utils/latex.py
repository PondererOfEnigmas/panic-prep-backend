import asyncio, aiofiles, re
from pathlib import Path
from fastapi import HTTPException
from loguru import logger

from src.config import settings
from src.utils.llm import call_llm_text, load_prompt_template


# redaction helper
_PATH_PAT = re.compile(
    r"""
    (                               # begin group 1
      (?:[A-Za-z]:)?                #   Windows drive letter, optional
      (?:[/\\][^ \n\r\t{}$&%#~^]+)+ #   one or more /segment   or  \segment
    )                               # end group 1
    """,
    re.VERBOSE,
)


def _scrub_paths(text: str) -> str:
    """
    Replace absolute or user-specific file paths with <PATH>.
    Keeps relative TeX references (e.g. ./image.pdf).
    """
    return _PATH_PAT.sub("<PATH>", text)


# pdflatex runner
async def _pdflatex(job_id: str) -> tuple[int, str]:
    cmd = ["pdflatex", "-interaction=nonstopmode", f"{job_id}.tex"]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=settings.workspace_root,
    )
    _, stderr = await proc.communicate()
    return proc.returncode, stderr.decode(errors="ignore")


# main compile+repair loop
async def compile_latex_with_retries(
    latex_code: str,
    job_id: str,
    max_rounds: int = 3,
) -> Path:
    """
    Compile LaTeX; on failure, redact path info, ask LLM to fix, and retry.
    """
    tex_path = settings.workspace_root / f"{job_id}.tex"

    async def _write(code: str):
        async with aiofiles.open(tex_path, "w", encoding="utf-8") as f:
            await f.write(code)

    current = latex_code
    for attempt in range(1, max_rounds + 1):
        await _write(current)
        rc, stderr = await _pdflatex(job_id)
        if rc == 0:
            # second pass for references—skip error handling
            if (await _pdflatex(job_id))[0] == 0:
                logger.info("pdflatex succeeded on attempt {}", attempt)
                return settings.workspace_root / f"{job_id}.pdf"

        # ---- on failure ------------------------------------------------------
        logger.warning("pdflatex failed (attempt {})", attempt)

        # collect tail of .log (typically more informative than stderr)
        log_path = settings.workspace_root / f"{job_id}.log"
        tail = ""
        if log_path.exists():
            tail = "\n".join(log_path.read_text(encoding="utf-8").splitlines()[-40:])

        error_snippet = _scrub_paths(stderr + "\n" + tail)

        if attempt == max_rounds:
            raise HTTPException(
                status_code=500,
                detail="LaTeX compilation failed after auto-repair attempts.",
            )

        # ask LLM to repair ----------------------------------------------------
        prompt = await load_prompt_template("latex_repair.prompt")
        fixed = await call_llm_text(
            prompt.format(
                error_snippet=error_snippet,
                latex_code=current,
                beamer="{beamer}",
                document="{document}",
            ),
            {},
        )
        if fixed.lstrip().startswith("```"):
            fixed = fixed.split("```")[1]
        current = fixed

    # should never reach here
    raise RuntimeError("compile_latex_with_retries: logic error")
