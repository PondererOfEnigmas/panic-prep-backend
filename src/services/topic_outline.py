from typing import List
import uuid

from fastapi import HTTPException
from loguru import logger

from src.utils.llm import load_prompt_template, call_llm_text
from src.services.materials_extraction import parse_topics_list


async def generate_outline(topics: List[str]) -> List[dict]:
    """
    1. Validate a plain list of topics.
    2. Render `topic_list_generator.prompt` with the topics.
    3. Call LLM (text) and parse the numbered list.
    4. If parsing fails (empty list), fall back to one entry per topic.
    """
    topics = [t.strip() for t in topics if t and t.strip()]
    if not topics:
        raise HTTPException(status_code=422, detail="no topic supplied")

    # 1) Load & interpolate prompt
    tpl = await load_prompt_template("topic_list_generator.prompt")
    prompt = tpl.replace(
        "[Insert topic or list of topics here]",
        ", ".join(topics),
    )

    # 2) LLM call
    raw = await call_llm_text(prompt, variables={})
    logger.debug("topic_outline raw LLM output:\n{}", raw)

    # 3) Parse into structured outline
    outline = parse_topics_list(raw)

    # 4) Fallback if empty
    if not outline:
        logger.warning(
            "parse_topics_list returned empty – falling back to input topics"
        )
        outline = [{"topic": t, "subtopics": []} for t in topics]

    return outline


def allocate_job_id() -> str:
    """Generate a UUID hex for topic-only jobs."""
    return uuid.uuid4().hex
