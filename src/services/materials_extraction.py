import base64
import asyncio
import subprocess
import re
from pathlib import Path
from typing import List, Dict, Any

from loguru import logger

from src.config import settings
from src.utils.llm import call_llm_multimedia, load_prompt_template

import aiofiles
import uuid


async def _convert_to_pdf(path: Path) -> Path:
    """
    Use Pandoc to convert any doc → PDF.
    """
    out = path.with_suffix(".pdf")
    cmd = [settings.pandoc_path, str(path), "-o", str(out)]
    await asyncio.to_thread(subprocess.run, cmd, check=True)
    return out


def _check_size(path: Path):
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > settings.materials_extraction_max_file_size_mb:
        raise ValueError(
            f"{path.name} is {size_mb:.1f}MB > {settings.materials_extraction_max_file_size_mb}MB"
        )


async def prepare_payload(
    material_keys: List[str],
) -> List[Dict[str, Any]]:
    """
    Build a Gemini‐compatible content array:
      - first element: prompt text (materials_extraction.prompt)
      - subsequent: base64 image_url entries (PDFs/images)
    """
    payload: List[Dict[str, Any]] = []

    # FIX: the case where material keys supplied are all empty, or wrong, or whatever..

    # 1) prompt text
    prompt_txt = await load_prompt_template("materials_extraction.prompt")
    payload.append({"type": "text", "text": prompt_txt})

    # 2) each file
    for key in material_keys:
        logger.debug(key)
        fp = settings.materials_dir / key
        if not fp.exists():
            raise FileNotFoundError(f"Missing material: {key}")
        logger.debug(fp)

        ext = fp.suffix.lower()
        if ext not in settings.materials_extraction_supported_formats:
            fp = await _convert_to_pdf(fp)
            ext = fp.suffix.lower()

        _check_size(fp)

        data = fp.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")

        if ext in [".jpg", ".jpeg", ".png"]:
            mime = f"image/{ext.lstrip('.')}"
        else:
            mime = "application/pdf"

        payload.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime};base64,{b64}",
                    "detail": "high",
                },
            }
        )

    return payload


async def extract_materials_analysis(
    material_keys: List[str],
) -> str:
    """
    Master entrypoint: package up materials → call Gemini → return raw content.
    """
    content_array = await prepare_payload(material_keys)
    return await call_llm_multimedia(content_array)


# — deep extraction + topics in one —


async def prepare_deep_payload(
    material_keys: List[str],
) -> List[Dict[str, Any]]:
    """
    Like prepare_payload, but swaps in the deep‐extraction prompt.
    """
    deep_prompt = await load_prompt_template("materials_extraction.prompt")
    # get the file‐entries from the normal payload (skip its prompt)
    file_entries = await prepare_payload(material_keys)
    # build new payload: deep prompt + file entries
    return [{"type": "text", "text": deep_prompt}] + file_entries[1:]


async def extract_and_structure(
    material_keys: List[str],
) -> Dict[str, str]:
    """
    1) Build Gemini payload with deep prompt + materials
    2) Call Gemini
    3) Parse out ANALYSIS and TOPICS
    4) Return dict { extracted_content, topics_list }
    """
    content_array = await prepare_deep_payload(material_keys)
    raw = await call_llm_multimedia(content_array)

    m = re.search(
        r"<<<ANALYSIS_START>>>(?P<analysis>.*?)<<<ANALYSIS_END>>>\s*"
        r"<<<TOPICS_START>>>(?P<topics>.*?)<<<TOPICS_END>>>",
        raw,
        flags=re.DOTALL,
    )
    if not m:
        raise ValueError("LLM output missing expected delimiters")

    return {
        "extracted_content": m.group("analysis").strip(),
        "topics_list": m.group("topics").strip(),
    }


async def analyze_and_structure_materials(
    material_keys: List[str],
) -> Dict[str, Any]:
    """
    Combines deep extraction + topic structuring **and**
    stores the extracted_content on disk under a job_id.

    Returns
    -------
    { "job_id": "<uuid>",
      "topics_list": "<raw topics list string from LLM>" }
    """
    # 1) run the existing deep-extraction flow
    extraction = await extract_and_structure(material_keys)

    job_id = uuid.uuid4().hex
    cache_path = settings.workspace_root / f"{job_id}_content.txt"

    # 2) persist extracted_content so later steps can pick it up
    async with aiofiles.open(cache_path, "w", encoding="utf-8") as f:
        await f.write(extraction["extracted_content"])

    return {
        "job_id": job_id,
        "topics_list": extraction["topics_list"],
    }
