from functools import lru_cache

from app.core.config import get_settings
from app.repositories.postgres_store import PostgresStore
from app.services.export_service import ExportService
from app.services.inference_service import InferenceService
from app.services.storage_service import StorageService
from app.services.task_service import TaskService
from app.services.vision_service import VisionService


@lru_cache
def get_store() -> PostgresStore:
    return PostgresStore(get_settings().database_url)


def get_storage_service() -> StorageService:
    settings = get_settings()
    return StorageService(settings.upload_dir)


def get_inference_service() -> InferenceService:
    return InferenceService(get_settings(), get_storage_service())


def get_task_service() -> TaskService:
    return TaskService(get_store(), get_inference_service())


def get_export_service() -> ExportService:
    return ExportService(get_store())


@lru_cache
def get_vision_service() -> VisionService:
    return VisionService(get_settings())
