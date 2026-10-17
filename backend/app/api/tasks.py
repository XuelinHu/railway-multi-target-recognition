from fastapi import APIRouter, Depends, HTTPException

from app.core.config import Settings, get_settings
from app.core.dependencies import get_store, get_task_service
from app.models.schemas import DetectTask, DetectionRequest
from app.repositories.postgres_store import PostgresStore
from app.services.task_service import TaskService


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("/detect", response_model=DetectTask, status_code=202)
def create_detection_task(
    request: DetectionRequest,
    task_service: TaskService = Depends(get_task_service),
    settings: Settings = Depends(get_settings),
    store: PostgresStore = Depends(get_store),
) -> DetectTask:
    if store.get_asset(request.asset_id) is None:
        raise HTTPException(status_code=404, detail="asset not found")
    task = task_service.create_detection_task(request)
    if settings.run_tasks_inline:
        task_service.run_detection(task.id)
        return store.get_task(task.id) or task
    return task


@router.get("", response_model=list[DetectTask])
def list_tasks(store: PostgresStore = Depends(get_store)) -> list[DetectTask]:
    return store.list_tasks()


@router.get("/{task_id}", response_model=DetectTask)
def get_task(task_id: str, store: PostgresStore = Depends(get_store)) -> DetectTask:
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task
