import os
import asyncio
from pathlib import Path

import aiofiles
from gradio_client import Client

from src.config import settings

# ─── Lazy‐initialized Gradio client ───────────────────────────────────────────
_client: Client | None = None


def get_kokoro_client() -> Client:
    """
    Instantiate the Gradio Client on first use, avoiding network calls at import time.
    Requires HF_KOKORO_REPO and HF_TOKEN environment variables.
    """
    global _client
    if _client is None:
        repo = os.getenv("HF_KOKORO_REPO")
        token = os.getenv("HF_TOKEN")
        if not repo or not token:
            raise RuntimeError(
                "Environment variables HF_KOKORO_REPO and HF_TOKEN must be set"
            )
        _client = Client(repo, hf_token=token)
    return _client


# ─── Synchronous TTS helper ───────────────────────────────────────────────────
def synthesize_text(text: str, voice: str) -> bytes:
    """
    Calls the Kokoro-TTS Gradio API via Client.predict, reads the generated .wav file,
    and returns its raw bytes.
    """
    client = get_kokoro_client()
    # client.predict returns (local_wav_path, phoneme_str)
    audio_path, _ = client.predict(
        text=text, voice=voice, speed=1, api_name="/generate_first"
    )
    with open(audio_path, "rb") as f:
        return f.read()


# ─── Async wrapper that writes out .mp3 and returns a public URL ─────────────
async def synthesize_tts(
    text: str,
    job_id: str,
    slide_index: int,
    voice: str,
) -> str:
    """
    1. Run blocking TTS in a thread to get WAV bytes.
    2. Write them as an .mp3 in {workspace_root}/audios/{job_id}/slide_{slide_index}.mp3.
    3. Return the web-accessible path.
    """
    # 1. Get raw audio bytes (WAV)
    audio_bytes = await asyncio.to_thread(synthesize_text, text, voice)

    # 2. Prepare output directory
    out_dir = Path(settings.workspace_root) / "audios" / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # 3. Write out as .mp3
    output_path = out_dir / f"slide_{slide_index}.mp3"
    async with aiofiles.open(output_path, "wb") as f:
        await f.write(audio_bytes)

    # 4. Return the public-facing path
    return f"/audios/{job_id}/slide_{slide_index}.mp3"
