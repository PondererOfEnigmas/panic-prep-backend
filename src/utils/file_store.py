#  src/utils/file_store.py
import os
import subprocess
import uuid
from pathlib import Path

from fastapi import UploadFile, HTTPException

from src.config import settings


# Build the allow-list once at import time
def _get_pandoc_input_formats() -> set[str]:
    """
    Call `pandoc --list-input-formats` once and cache the result.

    Returns
    -------
    set[str]
        {"docx", "markdown", "pptx", ...}
        (All lower-case, no leading dots.)
    """
    try:
        out = subprocess.check_output(
            ["pandoc", "--list-input-formats"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        )
        return {fmt.strip().lower() for fmt in out.splitlines() if fmt.strip()}
    except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        # Pandoc not installed or call failed → fall back to empty set.
        return set()


_PANDOC_INPUT_FORMATS: set[str] = _get_pandoc_input_formats()


def allowed_file(filename: str) -> bool:
    """
    Validate a filename against Pandoc’s supported input formats.

    Rules
    -----
    1. If the env var `PANDOC_ALLOW_ALL_FILES=true`, always return True.
    2. If `pandoc` could not be queried at import time, reject everything
       (unless the env var above is set).
    3. Otherwise, accept when the file extension – minus the leading dot –
       matches one of `pandoc --list-input-formats`.

    Examples
    --------
    >>> allowed_file("slides.pptx")
    True
    >>> allowed_file("malware.exe")
    False
    """
    if os.getenv("PANDOC_ALLOW_ALL_FILES", "").lower() == "true":
        return True

    if not _PANDOC_INPUT_FORMATS:
        # Pandoc missing and override not set ⇒ safest behaviour
        return False

    ext = Path(filename).suffix.lower().lstrip(".")
    return ext in _PANDOC_INPUT_FORMATS


def unique_name(original: str) -> str:
    return f"{uuid.uuid4().hex}_{original}"


async def save_upload(file: UploadFile) -> str:
    if not allowed_file(file.filename):
        raise HTTPException(status_code=415, detail="unsupported file type")

    target_name = unique_name(file.filename)
    target_path = Path(settings.materials_dir, target_name)

    # Read & write in chunks to avoid memory bloat
    with target_path.open("wb") as out_f:
        size = 0
        while chunk := await file.read(1 << 20):  # 1 MiB
            size += len(chunk)
            # Enforce per-file size limit from config
            if size > settings.max_attachment_size_mb * (1 << 20):
                target_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="file too large")
            out_f.write(chunk)

    return target_name
