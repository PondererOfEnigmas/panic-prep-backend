from fastapi import APIRouter, Depends, File, HTTPException, status, UploadFile
from pydantic import BaseModel

from src.utils.auth import verify_token
from src.services.materials import save_uploaded_materials

router = APIRouter(prefix="/presentation", tags=["presentation"])


class KeylistResponse(BaseModel):
    keys: list[str]


@router.post(
    "/upload_materials",
    response_model=KeylistResponse,
    status_code=status.HTTP_200_OK,
)
async def upload_materials(
    files: list[UploadFile] = File(...),
    _user=Depends(verify_token),
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
    return {"keys": keys}
