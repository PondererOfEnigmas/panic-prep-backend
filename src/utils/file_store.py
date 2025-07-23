import uuid
from pathlib import Path
from fastapi import UploadFile

from src.config import settings


def allowed_file(filename: str) -> bool:
    # TODO: set it up to allow anything Pandoc can open
    return True  # keep it permissive for now


def unique_name(original: str) -> str:
    return f"{uuid.uuid4().hex}_{original}"


async def save_upload(file: UploadFile) -> str:
    if not allowed_file(file.filename):
        raise ValueError("unsupported extension")

    target_name = unique_name(file.filename)
    target_path = Path(settings.materials_dir, target_name)

    # Read & write in chunks to avoid memory bloat
    with target_path.open("wb") as out_f:
        while chunk := await file.read(1024 * 1024):
            out_f.write(chunk)

    return target_name
