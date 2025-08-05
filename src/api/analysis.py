from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.services import materials_extraction as extraction_svc
from src.utils.auth import check_generation_limit, get_current_user, User

from src.services import topic_outline

router = APIRouter(prefix="/presentation", tags=["Analysis"])


class AnalysisRequest(BaseModel):
    material_keys: list[str]


class Topic(BaseModel):
    topic: str
    subtopics: list[str]


class AnalysisResponse(BaseModel):
    job_id: str
    outline: list[Topic]


@router.post(
    "/analyze_materials",
    response_model=AnalysisResponse,
    dependencies=[Depends(get_current_user), Depends(check_generation_limit)],
)
async def analyze_materials(
    payload: AnalysisRequest, user: User = Depends(get_current_user)
):
    """
    Deep-extracts material &amp; returns a job_id + draft topic list.
    """

    return await extraction_svc.analyze_and_structure_materials(payload.material_keys)


class TopicOutlineRequest(BaseModel):
    topics: list[str]


@router.post(
    "/topic_outline",
    response_model=AnalysisResponse,
    summary="Generate structured outline from plain topics (no materials).",
)
async def topic_outline_generator(
    payload: TopicOutlineRequest,
    _=Depends(check_generation_limit),
):
    outline = await topic_outline.generate_outline(payload.topics)
    # job_id blank to signal “no cached materials”
    return {"job_id": "", "outline": outline}
