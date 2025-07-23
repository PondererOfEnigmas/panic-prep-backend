import uvicorn
from src.api.app import create_app
from src.config import settings

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        workers=settings.uvicorn_workers,
        log_level=settings.log_level.lower(),
    )
