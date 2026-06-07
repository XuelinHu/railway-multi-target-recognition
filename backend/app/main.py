from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import annotations, assets, export, tasks
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(assets.router)
    app.include_router(tasks.router)
    app.include_router(annotations.router)
    app.include_router(export.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "inference_backend": settings.inference_backend}

    return app


app = create_app()
