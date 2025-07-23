from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List

from src.utils.auth import verify_token
from src.services.outline import extract_outline

router = APIRouter(tags=["topics"])


class OutlineRequest(BaseModel):
    material_keys: List[str]


class TopicOutline(BaseModel):
    topic: str
    subtopics: List[str]


class OutlineResponse(BaseModel):
    outline: List[TopicOutline]
    unsupported_attachments: List[str]


@router.post(
    "/topics/extract_outline",
    response_model=OutlineResponse,
    status_code=status.HTTP_200_OK,
)
async def topics_extract_outline(
    req: OutlineRequest,
    _user=Depends(verify_token),
):
    try:
        outline, unsupported = await extract_outline(req.material_keys)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return {"outline": outline, "unsupported_attachments": unsupported}
