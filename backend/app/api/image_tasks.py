from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.dependencies import get_store
from app.models.schemas import (
    ApiResponse,
    ImageTaskAnnotationUpdateRequest,
    ImageTaskCreateRequest,
    ImageTaskResult,
    ImageTaskResultSaveRequest,
    ImageTaskResultVersion,
    ImageTaskType,
)
from app.repositories.postgres_store import PostgresStore


router = APIRouter(prefix="/api/image-tasks", tags=["image-workspace"])


@router.post("/create", response_model=ApiResponse)
def create_image_task(
    request: ImageTaskCreateRequest,
    store: PostgresStore = Depends(get_store),
) -> ApiResponse:
    image = store.get_image_asset(request.image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="当前图片不存在")
    task = store.create_or_get_image_task(
        request.image_id,
        request.task_type,
        request.session_id or "default",
        request.user_id,
    )
    return ApiResponse(data=_task_payload(task))


@router.post("/result/save", response_model=ApiResponse)
def save_image_task_result(
    request: ImageTaskResultSaveRequest,
    store: PostgresStore = Depends(get_store),
) -> ApiResponse:
    if store.get_image_asset(request.image_id) is None:
        raise HTTPException(status_code=404, detail="当前图片不存在")
    result = ImageTaskResult(
        task_id=request.task_id,
        image_id=request.image_id,
        task_type=request.task_type,
        result_image_url=request.result_image_url,
        result_image_path=request.result_image_path,
        result_json=request.result_json,
        annotation_json=request.annotation_json,
        description_text=request.description_text,
        source=request.source,
        model_id=request.model_id,
    )
    saved, version = store.save_image_task_result(result)
    return ApiResponse(data={"resultId": saved.result_id, "versionId": version.version_id, "versionNo": version.version_no})


@router.get("/result/versions", response_model=ApiResponse)
def list_image_task_result_versions(
    image_id: str = Query(alias="imageId"),
    task_type: ImageTaskType = Query(alias="taskType"),
    session_id: str = Query(default="default", alias="sessionId"),
    store: PostgresStore = Depends(get_store),
) -> ApiResponse:
    versions = store.list_image_task_result_versions(image_id, task_type, session_id or "default")
    return ApiResponse(data=[_version_payload(version) for version in versions])


@router.get("/result/version/{version_id}", response_model=ApiResponse)
def get_image_task_result_version(
    version_id: str,
    store: PostgresStore = Depends(get_store),
) -> ApiResponse:
    version = store.get_image_task_result_version(version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="历史版本不存在")
    return ApiResponse(data=_version_payload(version))


@router.post("/result/version/{version_id}/restore", response_model=ApiResponse)
def restore_image_task_result_version(
    version_id: str,
    store: PostgresStore = Depends(get_store),
) -> ApiResponse:
    restored = store.restore_image_task_result_version(version_id)
    if restored is None:
        raise HTTPException(status_code=404, detail="历史版本不存在")
    result, version = restored
    return ApiResponse(data={**_result_payload(result), "versionId": version.version_id, "versionNo": version.version_no})


@router.get("/result", response_model=ApiResponse)
def get_image_task_result(
    image_id: str = Query(alias="imageId"),
    task_type: ImageTaskType = Query(alias="taskType"),
    session_id: str = Query(default="default", alias="sessionId"),
    store: PostgresStore = Depends(get_store),
) -> ApiResponse:
    result = store.get_image_task_result(image_id, task_type, session_id or "default")
    if result is None:
        return ApiResponse(message="no result", data=None)
    return ApiResponse(data=_result_payload(result))


@router.put("/annotation", response_model=ApiResponse)
def update_image_task_annotation(
    request: ImageTaskAnnotationUpdateRequest,
    store: PostgresStore = Depends(get_store),
) -> ApiResponse:
    result = store.update_image_task_annotation(
        request.task_id,
        request.image_id,
        request.task_type,
        request.annotation_json,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="当前任务结果不存在")
    return ApiResponse(data=_result_payload(result))


def _task_payload(task) -> dict:
    return {
        "taskId": task.task_id,
        "imageId": task.image_id,
        "taskType": task.task_type,
        "status": task.status,
        "createdAt": task.created_at.isoformat(),
        "updatedAt": task.updated_at.isoformat(),
    }


def _result_payload(result: ImageTaskResult) -> dict:
    return {
        "resultId": result.result_id,
        "taskId": result.task_id,
        "imageId": result.image_id,
        "taskType": result.task_type,
        "status": result.status,
        "resultImageUrl": result.result_image_url,
        "resultImagePath": result.result_image_path,
        "resultJson": result.result_json,
        "annotationJson": result.annotation_json,
        "descriptionText": result.description_text,
        "source": result.source,
        "modelId": result.model_id,
        "latestVersionId": result.latest_version_id,
        "latestVersionNo": result.latest_version_no,
        "createdAt": result.created_at.isoformat(),
        "updatedAt": result.updated_at.isoformat(),
    }


def _version_payload(version: ImageTaskResultVersion) -> dict:
    return {
        "versionId": version.version_id,
        "resultId": version.result_id,
        "taskId": version.task_id,
        "imageId": version.image_id,
        "taskType": version.task_type,
        "versionNo": version.version_no,
        "source": version.source,
        "modelId": version.model_id,
        "resultImageUrl": version.result_image_url,
        "resultImagePath": version.result_image_path,
        "resultJson": version.result_json,
        "annotationJson": version.annotation_json,
        "descriptionText": version.description_text,
        "createdAt": version.created_at.isoformat(),
    }
