import aiofiles
import uuid
from fastapi import HTTPException
from loguru import logger

from src.config import settings
from src.services.tts import synthesize_text
from src.utils.latex import compile_latex_with_retries
from src.utils.llm import call_llm_text, load_prompt_template

from src.utils.commands import generate_pdf_from_latex, convert_pdf_to_pngs
import json

import re


async def _load_cached_content(job_id: str) -> str:
    path = settings.workspace_root / f"{job_id}_content.txt"
    if not path.exists():
        raise HTTPException(status_code=404, detail="job_id not found / expired")
    async with aiofiles.open(path, "r", encoding="utf-8") as f:
        return await f.read()


async def create_slides_from_outline(
    job_id: str, outline: list[dict], cached=True
) -> list[str]:
    """
    1. Try to load cached extracted_content (materials flow).
    2. Select the appropriate Beamer prompt.
    3. Call LLM to generate LaTeX, compile to PDF, convert to PNGs.
    4. Return the list of slide PNG URLs.
    """
    if cached:
        extracted_content = await _load_cached_content(job_id)
    else:
        extracted_content = None

    prompt_name = (
        "beamer_generator.prompt" if extracted_content else "beamer_topics_only.prompt"
    )
    tpl = await load_prompt_template(prompt_name)

    # Simple replacement for backward-compatible templates
    prompt = tpl.replace("{{extracted_content}}", extracted_content or "").replace(
        "{{outline}}", str(outline)
    )

    latex = await call_llm_text(
        prompt,
        {},
    )
    if latex.lstrip().startswith("```"):
        latex = latex.split("```")[1]

    latex = re.sub(r"\\pause\s*", "", latex)  # scrub stray \pause commands

    tex_dir = settings.workspace_root / job_id
    tex_dir.mkdir(parents=True, exist_ok=True)
    tex_path = tex_dir / "presentation.tex"
    tex_path.write_text(latex, encoding="utf-8")

    pdf_path = await compile_latex_with_retries(latex, job_id)
    png_urls = await convert_pdf_to_pngs(pdf_path, job_id)

    logger.info("Generated {} slides for job {}", len(png_urls), job_id)
    return png_urls


async def generate_narrations(job_id: str) -> list[dict]:
    tex_path = settings.workspace_root / job_id / "presentation.tex"
    if not tex_path.exists():
        raise HTTPException(404, f"No presentation for job {job_id}")
    beamer_code = tex_path.read_text(encoding="utf-8")

    tpl = await load_prompt_template("narration_generator.prompt")
    prompt = tpl.replace("{{beamer_code}}", beamer_code)

    raw = await call_llm_text(prompt, {"beamer_code": beamer_code})

    # Strip leading/trailing Markdown code fences (``` or ```json)
    # 1. Remove opening fence
    raw_clean = re.sub(r"^```(?:\w+)?\s*\n?", "", raw)
    # 2. Remove closing fence
    raw_clean = re.sub(r"\n?```$", "", raw_clean).strip()

    try:
        return json.loads(raw_clean)
    except json.JSONDecodeError:
        logger.debug("Failed JSON parse, raw LLM output:\n%s", raw)
        raise HTTPException(500, "Invalid JSON from narration LLM")
