from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List

from src.services import presentation as pres_svc
from src.utils.auth import get_current_user, User, check_generation_limit

router = APIRouter(prefix="/presentation", tags=["Presentation"])


class BuildSlidesPayload(BaseModel):
    job_id: str = Field(
        ..., description="job_id obtained from /presentation/analyze_materials"
    )
    outline: List[dict] = Field(
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

    return await pres_svc.create_slides_from_outline(payload.job_id, payload.outline)


# TODO: /build_presentation
# TODO: support /build_slides and /build_presentation
# through just a refined list of topics too
# (use beamer_topics_only.prompt..)
