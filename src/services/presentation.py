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


async def create_slides_from_outline(job_id: str, outline: list[dict]) -> list[str]:
    """
    1. Read cached extracted_content.
    2. Prompt LLM → Beamer LaTeX using BOTH content & outline.
    3. Build PDF & convert to PNGs.
    4. Return /pngs/… URLs (ordered).
    """
    extracted_content = await _load_cached_content(job_id)

    # prompt_tpl = await load_prompt_template("beamer_generator.prompt")
    # prompt = prompt_tpl.format(
    #     extracted_content=extracted_content,
    #     outline=outline,  # pydantic serialises list nicely
    # )

    tpl = await load_prompt_template("beamer_generator.prompt")
    prompt = tpl.replace("{{extracted_content}}", extracted_content).replace(
        "{{outline}}", str(outline)
    )

    latex = await call_llm_text(
        prompt,
        {},
        # variables={"extracted_content": extracted_content, "outline": outline},
    )

    # if model wrapped result in ```latex blocks
    if latex.lstrip().startswith("```"):
        latex = latex.split("```")[1]

    tex_dir = settings.workspace_root / job_id
    tex_dir.mkdir(parents=True, exist_ok=True)  # ensure job dir exists
    tex_path = tex_dir / "presentation.tex"
    tex_path.write_text(latex, encoding="utf-8")  # **save .tex file**

    pdf_path = await compile_latex_with_retries(
        latex, job_id
    )  # instead of generate_pdf_from_latex(...)
    png_urls = await convert_pdf_to_pngs(pdf_path, job_id)

    # delete cache so disk doesn&#x27;t bloat
    # (settings.workspace_root / f"{job_id}_content.txt").unlink(missing_ok=True)

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
