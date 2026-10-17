from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import require_user
from app.core.dependencies import get_store, get_training_service
from app.models.schemas import ApiResponse, AuthUser, ImageTaskType, TrainingTask
from app.repositories.postgres_store import PostgresStore
from app.services.training_service import TrainingService

router = APIRouter(prefix="/api/training", tags=["training"])


class TrainingCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    task_type: str = Field(alias="taskType")
    model_name: str = Field(alias="modelName")
    train_image_ids: list[str] = Field(alias="trainImageIds", min_length=1)
    val_image_ids: list[str] = Field(alias="valImageIds", min_length=1)
    epochs: int = Field(default=50, ge=1, le=1000)
    batch_size: int = Field(default=8, ge=1, le=256)
    image_size: int = Field(default=640, ge=128, le=2048)

    model_config = {"populate_by_name": True}


@router.get("/images", response_model=ApiResponse)
def training_images(
    task_type: ImageTaskType,
    page: int = 1,
    page_size: int = 200,
    store: PostgresStore = Depends(get_store),
    current_user: AuthUser = Depends(require_user),
) -> ApiResponse:
    records, total = store.list_image_assets(task_type=task_type, user_id=None if current_user.role in {"admin", "reviewer"} else current_user.user_id, page=page, page_size=min(page_size, 500))
    return ApiResponse(data={"records": [{"imageId": item.image_id, "name": item.original_name, "hasResult": item.has_current_task_result, "status": item.task_status, "width": item.width, "height": item.height} for item in records if item.has_current_task_result], "total": total})


@router.get("/tasks", response_model=ApiResponse)
def list_training_tasks(store: PostgresStore = Depends(get_store), _: AuthUser = Depends(require_user)) -> ApiResponse:
    return ApiResponse(data=[task.model_dump(mode="json", by_alias=True) for task in store.list_training_tasks()])


@router.get("/tasks/{training_id}", response_model=ApiResponse)
def get_training_task(training_id: str, store: PostgresStore = Depends(get_store), _: AuthUser = Depends(require_user)) -> ApiResponse:
    task = store.get_training_task(training_id)
    if task is None:
        raise HTTPException(status_code=404, detail="training task not found")
    return ApiResponse(data={"task": task.model_dump(mode="json", by_alias=True), "metrics": [metric.model_dump(mode="json", by_alias=True) for metric in store.list_training_metrics(training_id)]})


@router.post("/tasks", response_model=ApiResponse, status_code=202)
def create_training_task(
    request: TrainingCreateRequest,
    store: PostgresStore = Depends(get_store),
    training: TrainingService = Depends(get_training_service),
    current_user: AuthUser = Depends(require_user),
) -> ApiResponse:
    if current_user.role == "reviewer":
        raise HTTPException(status_code=403, detail="reviewers cannot start training")
    if request.task_type not in {"detection", "segmentation", "pose"}:
        raise HTTPException(status_code=400, detail="unsupported training task type")
    all_ids = set(request.train_image_ids + request.val_image_ids)
    for image_id in all_ids:
        if store.get_accessible_image_asset(image_id, current_user.user_id) is None:
            raise HTTPException(status_code=404, detail=f"image not accessible: {image_id}")
    task = TrainingTask(
        name=request.name, task_type=request.task_type, model_name=request.model_name,
        train_image_ids=request.train_image_ids, val_image_ids=request.val_image_ids,
        epochs=request.epochs, batch_size=request.batch_size, image_size=request.image_size,
    )
    store.create_training_task(task)
    training.start(task)
    return ApiResponse(data=task.model_dump(mode="json", by_alias=True))
