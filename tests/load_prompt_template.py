import asyncio
from pathlib import Path
from textwrap import dedent

import pytest

from src.utils.llm import load_prompt_template
from src.config import settings


@pytest.mark.anyio
async def test_loads_real_prompt(tmp_path):
    # Create a throw-away prompts dir with a fake prompt file
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    expected = dedent(
        """
        ### Test Prompt
        Give me something interesting.
        """
    ).strip()
    (prompts_dir / "my_fake.prompt").write_text(expected, encoding="utf-8")

    # Patch settings.prompts_dir just for this test
    original = settings.prompts_dir
    settings.prompts_dir = prompts_dir
    try:
        content = await load_prompt_template("my_fake.prompt")
        assert content == expected
    finally:
        settings.prompts_dir = original
