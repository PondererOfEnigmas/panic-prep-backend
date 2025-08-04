import base64
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.config import settings
from src.services import materials_extraction as me


@pytest.fixture(autouse=True)
def _mock_prompt_loader(monkeypatch):
    """
    Replace `load_prompt_template()` with a trivial async stub for **all**
    tests in this module.
    """
    monkeypatch.setattr(
        me, "load_prompt_template", AsyncMock(return_value="dummy prompt")
    )


# Helpers                                                                     #
@pytest.fixture()
def dummy_pdf(tmp_path: Path) -> Path:
    fp = tmp_path / f"{uuid.uuid4().hex}.pdf"
    fp.write_bytes(b"%PDF-1.4\n%EOF")
    return fp


def _copy_to_materials(src: Path) -> None:
    dest = Path(settings.materials_dir, src.name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(src.read_bytes())


#  Tests                                                                       #
@pytest.mark.anyio
async def test_empty_keys():
    with pytest.raises(HTTPException) as exc:
        await me.prepare_payload([])
    assert exc.value.status_code == 422


@pytest.mark.anyio
async def test_nonexistent_key():
    with pytest.raises(HTTPException) as exc:
        await me.prepare_payload(["does-not-exist.pdf"])
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_success(dummy_pdf):
    _copy_to_materials(dummy_pdf)

    payload = await me.prepare_payload([dummy_pdf.name])

    assert payload[0] == {"type": "text", "text": "dummy prompt"}
    assert payload[1]["type"] == "image_url"

    url = payload[1]["image_url"]["url"]
    assert url.startswith("data:application/pdf;base64,")
    base64.b64decode(url.split(",", 1)[1], validate=True)
