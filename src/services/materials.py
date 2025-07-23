from uuid import uuid4
from pathlib import Path
from typing import List

from fastapi import HTTPException, status, UploadFile

from src.config import settings


async def save_uploaded_materials(files: List[UploadFile]) -> List[str]:
    """
    Validate & save multiple UploadFile objects under materials_dir.
    - Enforces max number of attachments.
    - Enforces per-file size limit.
    - Cleans up on any failure.
    Returns list of generated keys (uuid_filename.ext).
    """
    # 1) Validate count
    if len(files) > settings.max_attachments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many files: {len(files)} > {settings.max_attachments}",
        )

    saved_keys: List[str] = []
    max_bytes = settings.max_attachment_size_mb * 1024 * 1024

    # 2) Process each file
    for upload in files:
        filename = Path(upload.filename).name
        key = f"{uuid4().hex}_{filename}"
        dest = settings.materials_dir / key
        bytes_written = 0

        try:
            # Stream in chunks so we can enforce size limit
            with open(dest, "wb") as out_file:
                while True:
                    chunk = await upload.read(1024 * 1024)  # 1 MB
                    if not chunk:
                        break
                    bytes_written += len(chunk)
                    if bytes_written > max_bytes:
                        # Exceeded size → cleanup and abort
                        out_file.close()
                        dest.unlink(missing_ok=True)
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=(
                                f"File '{filename}' is "
                                f"{bytes_written/(1024*1024):.2f} MB > "
                                f"{settings.max_attachment_size_mb} MB"
                            ),
                        )
                    out_file.write(chunk)

            saved_keys.append(key)

        except HTTPException:
            # Propagate validation errors
            raise

        except Exception:
            # On any other error, cleanup everything so far
            if dest.exists():
                dest.unlink(missing_ok=True)
            for k in saved_keys:
                (settings.materials_dir / k).unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed saving file '{filename}'",
            )

    return saved_keys
