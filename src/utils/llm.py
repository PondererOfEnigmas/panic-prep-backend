import aiofiles
import asyncio
import litellm
from typing import Any, List, Dict

from loguru import logger

from src.config import settings


async def load_prompt_template(name: str) -> str:
    """
    Load a prompt template from prompts_dir.
    """
    # logger.debug(name)
    p = settings.prompts_dir / name

    async with aiofiles.open(p, "r", encoding="utf-8") as f:
        return await f.read()


async def call_llm_text(prompt: str, variables: Dict[str, Any]) -> str:
    """
    For purely text‐based prompts (e.g. outline extraction).
    """
    # template = await load_prompt_template(prompt_name)
    # prompt = template.format(**variables)
    #
    # logger.debug(f"{template=}")
    # logger.debug(f"{prompt=}")

    def _sync_call():
        return litellm.completion(
            model=settings.materials_extraction_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=settings.materials_extraction_max_tokens,
            temperature=0.2,
        )

    response = await asyncio.to_thread(_sync_call)
    return response.choices[0].message.content


async def call_llm_multimedia(content_array: List[Dict[str, Any]]) -> str:
    """
    For image/pdf + prompt‐template payloads.
    """

    def _sync_call():
        return litellm.completion(
            model=settings.materials_extraction_model,
            messages=[{"role": "user", "content": content_array}],
            max_tokens=settings.materials_extraction_max_tokens,
            temperature=0.2,
        )

    response = await asyncio.to_thread(_sync_call)
    return response.choices[0].message.content
