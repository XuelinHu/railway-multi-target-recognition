from functools import lru_cache

from app.core.config import get_settings
from app.repositories.json_store import JsonStore
from app.services.export_service import ExportService
from app.services.inference_service import InferenceService
from app.services.storage_service import StorageService
from app.services.task_service import TaskService


@lru_cache
def get_store() -> JsonStore:
    return JsonStore(get_settings().db_path)


def get_storage_service() -> StorageService:
    settings = get_settings()
    return StorageService(settings.upload_dir)


def get_inference_service() -> InferenceService:
    return InferenceService(get_settings())


def get_task_service() -> TaskService:
    return TaskService(get_store(), get_inference_service())


def get_export_service() -> ExportService:
    return ExportService(get_store())
