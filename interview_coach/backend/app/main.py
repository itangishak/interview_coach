import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.utils.logger import setup_logging


def _init_blocking_singletons():
    """Pre-warm all heavy singletons in a background thread.

    DatabaseManager, SessionService, and UserProfileService all run
    synchronous SQLite I/O inside __init__.  Triggering creation
    here — outside the asyncio event loop — avoids freezing the
    WebSocket handshake.
    """
    from app.services.session_service import SessionService
    from app.services.user_profile_service import UserProfileService

    SessionService()
    UserProfileService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: pre-initialize blocking singletons before startup."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _init_blocking_singletons)
    yield


def create_app(**config_overrides) -> FastAPI:
    settings = get_settings(**config_overrides)
    setup_logging(settings.paths.get("logs", "./logs"))

    app = FastAPI(
        title=settings.app.name,
        version=settings.app.version,
        debug=settings.app.debug,
        lifespan=lifespan,
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
