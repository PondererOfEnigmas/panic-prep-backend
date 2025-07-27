from fastapi import APIRouter, Depends, File, HTTPException, status, UploadFile
from pydantic import BaseModel

from src.utils.auth import get_current_user
from src.services.materials import save_uploaded_materials


router = APIRouter(prefix="/presentation", tags=["presentation"])


class KeylistResponse(BaseModel):
    material_keys: list[str]


@router.post(
    "/upload_materials",
    response_model=KeylistResponse,
    status_code=status.HTTP_200_OK,
)
async def upload_materials(
    files: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
):
    """
    Upload up to max_attachments files, each <= max_attachment_size_mb.
    Returns a list of storage keys.
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided",
        )

    keys = await save_uploaded_materials(files)
    return {"material_keys": keys}
