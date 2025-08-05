from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from loguru import logger

from src.services import presentation as pres_svc
from src.services.presentation import generate_narrations
from src.services.topic_outline import allocate_job_id
from src.services.tts import synthesize_tts
from src.utils.auth import get_current_user, User, check_generation_limit
from src.config import settings

from src.services.presentation import stitch_video

router = APIRouter(prefix="/presentation", tags=["Presentation"])


class BuildSlidesPayload(BaseModel):
    job_id: str = Field("", description="Optional; blank for topic‐only flow")
    outline: List[dict] = Field(
        ...,
        example=[{"topic": "Chain rule", "subtopics": ["definition", "examples"]}],
    )


# FIX: these and other commands involving a job_id, can only be performed by user that initiated a job_id..


@router.post(
    "/build_slides",
    response_model=List[str],
    dependencies=[Depends(check_generation_limit)],
)
async def build_slides(
    payload: BuildSlidesPayload,
    user: User = Depends(get_current_user),
):
    if not payload.outline:
        raise HTTPException(status_code=422, detail="Outline cannot be empty")

    # Use provided job_id or allocate a new one for topic-only
    cached = False if not payload.job_id else True
    job_id = payload.job_id or allocate_job_id()
    png_urls = await pres_svc.create_slides_from_outline(
        job_id, payload.outline, cached
    )
    return png_urls


class SlideWithAudio(BaseModel):
    slideIndex: int
    title: str
    slide_png_url: str
    audio_url: str


class BuildPresentationPayload(BaseModel):
    job_id: str = Field("", description="Optional; blank for topic‐only flow")
    outline: List[dict]
    voice: Optional[str] = Field(None, description="Optional Kokoro voice")


@router.post(
    "/build_presentation",
    response_model=List[SlideWithAudio],
    dependencies=[Depends(get_current_user), Depends(check_generation_limit)],
)
async def build_presentation(payload: BuildPresentationPayload):
    if not payload.outline:
        raise HTTPException(status_code=422, detail="Outline cannot be empty")

    voice = payload.voice or settings.kokoro_voice_default
    job_id = payload.job_id or allocate_job_id()

    cached = False if not payload.job_id else True

    # 1) Generate slides (topic-only or materials-based)
    png_urls = await pres_svc.create_slides_from_outline(
        job_id, payload.outline, cached
    )

    # 2) Generate slide narrations metadata
    narrations = await generate_narrations(job_id)

    if len(narrations) != len(png_urls):
        raise HTTPException(
            status_code=500,
            detail="Mismatch between slides and narration count",
        )

    logger.info(f"Generating TTS for {len(narrations)} slides (job {job_id})")

    # 3) Synthesize TTS and assemble response
    results: List[SlideWithAudio] = []
    for slide in narrations:
        idx = slide["slideIndex"]
        title = slide.get("title", "")
        text = slide.get("narration", "")

        audio_url = await synthesize_tts(text, job_id, idx, voice)

        try:
            png_url = next(u for u in png_urls if job_id in u and f"{idx}.png" in u)
        except StopIteration:
            raise HTTPException(
                status_code=500,
                detail=f"Could not find PNG for slide {idx}",
            )

        results.append(
            SlideWithAudio(
                slideIndex=idx,
                title=title,
                slide_png_url=png_url,
                audio_url=audio_url,
            )
        )

    return results


class DownloadVideoRequest(BaseModel):
    job_id: str


@router.post(
    "/download_video",
    summary="Get the URL of the stitched MP4 for a completed job",
)
async def download_video(
    body: DownloadVideoRequest,
    user: User = Depends(get_current_user),
    _=Depends(check_generation_limit),
):
    """
    Ensures the video is stitched, then returns its mounted URL under /videos/.
    """
    video_path = await stitch_video(body.job_id)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")

    # assuming StaticFiles is mounted at '/videos' pointing to settings.video_dir
    url = f"/videos/{video_path.name}"
    return {"video_url": url}
