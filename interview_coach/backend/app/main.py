from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.utils.logger import setup_logging


def create_app(**config_overrides) -> FastAPI:
    settings = get_settings(**config_overrides)
    setup_logging(settings.paths.get("logs", "./logs"))

    app = FastAPI(
        title=settings.app.name,
        version=settings.app.version,
        debug=settings.app.debug,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "app": settings.app.name,
            "calibration_available": settings.calibration_available,
        }

    app.include_router(api_router)
    return app


app = create_app()