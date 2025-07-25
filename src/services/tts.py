import os
from pathlib import Path

import aiofiles
from gradio_client import Client

from src.config import settings  # make sure settings.workspace_root is a pathlib.Path

client = Client(os.environ["HF_KOKORO_REPO"], hf_token=os.environ["HF_TOKEN"])


def synthesize_text(text: str, voice: str) -> bytes:
    """
    Calls the Kokoro-TTS Gradio API, reads the generated .wav file,
    and returns its bytes.
    """
    # client.predict returns (local_wav_path, phoneme_str)
    audio_path, _ = client.predict(
        text=text, voice=voice, speed=1, api_name="/generate_first"
    )
    # Read and return the binary contents
    with open(audio_path, "rb") as f:
        return f.read()


async def synthesize_tts(text: str, job_id: str, slide_index: int, voice: str) -> str:
    """
    Generates TTS bytes for `text`, writes them as an .mp3 in:
      {workspace_root}/{job_id}/audios/slide_{slide_index}.mp3
    and returns the public-facing path.
    """
    # 1. Synthesize raw audio bytes (wav)
    audio_bytes = synthesize_text(text, voice)

    # 2. Prepare output directory
    out_dir: Path = settings.workspace_root / "audios" / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # 3. Write out as .mp3
    output_path: Path = out_dir / f"slide_{slide_index}.mp3"
    async with aiofiles.open(output_path, "wb") as f:
        await f.write(audio_bytes)

    # 4. Return the web-accessible path
    return f"/audios/{job_id}/slide_{slide_index}.mp3"
