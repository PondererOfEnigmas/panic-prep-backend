import uvicorn
from src.api.app import create_app
from src.config import settings

app = create_app()


def main():
    # Base Uvicorn config
    uvicorn_cfg = {
        "host": settings.host or "0.0.0.0",
        "port": settings.port or 8000,
        "log_level": settings.log_level.lower(),
    }

    if settings.dev_mode:
        # Development-specific settings
        uvicorn_cfg.update(
            {
                "reload": True,
                "reload_includes": ["*.py"],
                "reload_excludes": ["*.tmp"],
            }
        )
    else:
        uvicorn_cfg["workers"] = settings.uvicorn_workers

    uvicorn.run("src.main:app", **uvicorn_cfg)


if __name__ == "__main__":
    main()
