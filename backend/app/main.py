from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import ai, annotations, assets, export, image_tasks, images, tasks, vision
from app.core.config import get_settings
from app.core.dependencies import get_store, get_task_service
from app.services.task_worker import DatabaseTaskWorker


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        worker = None
        if settings.task_worker_enabled and not settings.run_tasks_inline:
            worker = DatabaseTaskWorker(
                get_store(),
                get_task_service(),
                settings.task_poll_interval_seconds,
            )
            worker.start()
        try:
            yield
        finally:
            if worker is not None:
                worker.stop()
            get_store().close()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
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
    app.include_router(vision.router)
    app.include_router(images.router)
    app.include_router(image_tasks.router)
    app.include_router(ai.router)
    app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

    @app.get("/health")
    def health() -> dict[str, str]:
        database_status = "ok" if get_store().healthcheck() else "unavailable"
        return {
            "status": "ok",
            "database": database_status,
            "inference_backend": settings.inference_backend,
        }

    return app


app = create_app()
