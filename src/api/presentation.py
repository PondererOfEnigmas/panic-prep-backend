from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.services import presentation as pres_svc
from src.services.presentation import generate_narrations
from src.utils.auth import get_current_user, User, check_generation_limit

from src.services.tts import synthesize_tts

from src.config import settings
from typing import Optional

from loguru import logger


router = APIRouter(prefix="/presentation", tags=["Presentation"])


class BuildSlidesPayload(BaseModel):
    job_id: str = Field(
        ..., description="job_id obtained from /presentation/analyze_materials"
    )
    outline: list[dict] = Field(
        ...,
        example=[{"topic": "Chain rule", "subtopics": ["definition", "examples"]}],
    )


@router.post(
    "/build_slides",
    response_model=list[str],
    dependencies=[Depends(check_generation_limit)],
)
async def build_slides(
    payload: BuildSlidesPayload,
    user: User = Depends(get_current_user),
):
    if not payload.outline:
        raise HTTPException(status_code=422, detail="Outline cannot be empty")

    png_urls = await pres_svc.create_slides_from_outline(
        payload.job_id, payload.outline
    )

    return png_urls


class SlideWithAudio(BaseModel):
    slideIndex: int
    title: str
    slide_png_url: str
    audio_url: str


class BuildPresentationPayload(BaseModel):
    job_id: str
    outline: list[dict]
    voice: Optional[str] = Field(None, description="optional Kokoro voice")


@router.post(
    "/build_presentation",
    response_model=list[SlideWithAudio],
    dependencies=[Depends(get_current_user), Depends(check_generation_limit)],
)
async def build_presentation(payload: BuildPresentationPayload):
    voice = payload.voice or settings.kokoro_voice_default

    png_urls = await pres_svc.create_slides_from_outline(
        payload.job_id, payload.outline
    )

    # latex_code, png_urls = await asyncio.to_thread(
    #     pres_svc.create_slides_from_outline, payload.job_id, payload.outline
    # )

    # narrations = await asyncio.to_thread(generate_narrations, payload.job_id)
    narrations = await generate_narrations(payload.job_id)

    # return narrations

    results = []

    assert len(narrations) == len(png_urls)

    logger.info(f"starting to generate TTS for {len(narrations)} slides")

    for slide in narrations:
        idx = slide["slideIndex"]
        audio_url = await synthesize_tts(slide["narration"], payload.job_id, idx, voice)
        try:
            png_url = next(
                u for u in png_urls if payload.job_id in u and f"{idx}.png" in u
            )
        except StopIteration:
            raise Exception("Mismtach in slide numbering/path")
        results.append(
            {
                "slideIndex": idx,
                "title": slide["title"],
                "slide_png_url": png_url,
                "audio_url": audio_url,
            }
        )

    return results


# TODO: support /build_slides and /build_presentation
# through just a refined list of topics too
# (use beamer_topics_only.prompt..)
