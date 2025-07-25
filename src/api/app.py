from fastapi.staticfiles import StaticFiles

from fastapi import FastAPI
from loguru import logger
from contextlib import asynccontextmanager

from src.config import settings
from src.api.materials import router as materials_router
from src.api.analysis import router as analysis_router
from src.api.presentation import router as presentation_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("panic-prep starting (workers={})", settings.uvicorn_workers)
    yield
    logger.info("panic-prep shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="panic-prep",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(materials_router)
    app.include_router(analysis_router)
    app.include_router(presentation_router)

    @app.get("/healthz", tags=["aux"])
    async def healthz():
        return {"ok": True}

    @app.get("/version", tags=["aux"])
    async def version():
        return {
            "version": app.version,
            "uvicorn_workers": settings.uvicorn_workers,
        }

    # expose generated artefacts
    app.mount("/pngs", StaticFiles(directory=settings.pngs_dir), name="pngs")
    app.mount(
        "/materials", StaticFiles(directory=settings.materials_dir), name="materials"
    )

    app.mount(
        "/audios",
        StaticFiles(directory=str(settings.audios_dir), html=False),
        name="audios",
    )
    return app
