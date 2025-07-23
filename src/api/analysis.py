from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.services import materials_extraction as extraction_svc
from src.utils.auth import get_current_user, User

router = APIRouter(prefix="/presentation", tags=["Analysis"])


class AnalysisRequest(BaseModel):
    material_keys: list[str]


class AnalysisResponse(BaseModel):
    job_id: str
    topics_list: str  # raw string; client edits into structured outline


@router.post("/analyze_materials", response_model=AnalysisResponse)
async def analyze_materials(
    payload: AnalysisRequest, user: User = Depends(get_current_user)
):
    """
    Deep-extracts material &amp; returns a job_id + draft topic list.
    """

    # TODO: implement check for how many generations/analyses the user has already made..
    return await extraction_svc.analyze_and_structure_materials(payload.material_keys)


# TODO: implement a topic list generator endpoint that uses topic_list_generator.prompt
