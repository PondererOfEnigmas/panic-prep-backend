import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT_DIR / "prompts"
TMP_ROOT = ROOT_DIR / "tmp"

# Load .env
ENV_FILE = ROOT_DIR / ".env"
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE, override=False)


# Config Dataclass
@dataclass
class Config:
    host: str = "0.0.0.0"
    port: int = 8000

    # Auth
    supabase_url: str = field(default_factory=lambda: os.environ["SUPABASE_URL"])
    supabase_jwk_url: str = field(
        default_factory=lambda: os.environ["SUPABASE_JWK_URL"]
    )
    supabase_service_key: str = field(
        default_factory=lambda: os.environ["SUPABASE_SERVICE_KEY"]
    )
    supabase_anon_key: str = field(
        default_factory=lambda: os.environ["SUPABASE_ANON_KEY"]
    )

    pandoc_path: str = field(default_factory=lambda: os.getenv("PANDOC_PATH", "pandoc"))
    ffmpeg_path: str = field(default_factory=lambda: os.getenv("FFMPEG_PATH", "ffmpeg"))
    pdftoppm_path: str = field(
        default_factory=lambda: os.getenv("PDFTOPPM_PATH", "pdftoppm")
    )

    # Upload limits
    max_attachments: int = field(
        default_factory=lambda: int(os.getenv("MAX_ATTACHMENTS", "5"))
    )
    max_attachment_size_mb: int = field(
        default_factory=lambda: int(os.getenv("MAX_ATTACHMENT_SIZE_MB", "10"))
    )

    # Generation caps
    max_gen_per_day: int = field(
        default_factory=lambda: int(os.getenv("MAX_GEN_PER_DAY", "20"))
    )

    # External binaries
    ffmpeg_path: str = field(default_factory=lambda: os.getenv("FFMPEG_PATH", "ffmpeg"))
    pdftoppm_path: str = field(
        default_factory=lambda: os.getenv("PDFTOPPM_PATH", "pdftoppm")
    )

    # Workspace root (project-local tmp)
    workspace_root: Path = field(default_factory=lambda: TMP_ROOT)

    # Subdirectories (created in __post_init__)
    materials_dir: Path = field(init=False)
    pngs_dir: Path = field(init=False)
    audios_dir: Path = field(init=False)
    videos_dir: Path = field(init=False)

    # Prompts
    prompts_dir: Path = field(default_factory=lambda: PROMPTS_DIR)

    # Runtime
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "DEBUG"))
    uvicorn_workers: int = field(
        default_factory=lambda: int(os.getenv("UVICORN_WORKERS", "4"))
    )

    materials_extraction_supported_formats: list[str] = field(
        default_factory=lambda: [".pdf", ".jpg", ".jpeg", ".png"]
    )
    materials_extraction_max_file_size_mb: int = field(
        default_factory=lambda: int(
            os.getenv("materials_extraction_MAX_FILE_SIZE_MB", "20")
        )
    )
    materials_extraction_model: str = field(
        default_factory=lambda: os.getenv(
            "materials_extraction_MODEL", "gemini/gemini-2.5-pro"
        )
    )

    # materials_extraction_model: str = field(
    #     default_factory=lambda: os.getenv(
    #         "materials_extraction_MODEL", "gemini/gemini-2.5-flash"
    #     )
    # )
    materials_extraction_max_tokens: int = field(
        default_factory=lambda: int(
            os.getenv("materials_extraction_MAX_TOKENS", "32768")
        )
    )

    kokoro_voice_default: str = "af_heart"
    dev_mode: bool = True

    def __post_init__(self):
        # Ensure workspace structure
        for sub in ("", "materials", "pngs", "audios", "videos"):
            path = self.workspace_root / sub
            path.mkdir(parents=True, exist_ok=True)

        self.materials_dir = self.workspace_root / "materials"
        self.pngs_dir = self.workspace_root / "pngs"
        self.audios_dir = self.workspace_root / "audios"
        self.videos_dir = self.workspace_root / "videos"


# Instantiate global settings
settings = Config()

# Loguru setup
logger.remove()
LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>"
)
logger.add(
    sys.stderr,
    level=settings.log_level.upper(),
    format=LOG_FORMAT,
    enqueue=True,
    backtrace=False,
    diagnose=False,
)


logger.debug(f"{ROOT_DIR=}")

logger.debug(
    "Configuration loaded: {}",
    {
        "supabase_url": settings.supabase_url,
        "workspace_root": str(settings.workspace_root),
        "prompts_dir": str(settings.prompts_dir),
        "log_level": settings.log_level,
        "uvicorn_workers": settings.uvicorn_workers,
    },
)
