from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_store
from app.models.schemas import ApiResponse, LabelConfigCreateRequest, LabelConfigUpdateRequest
from app.repositories.postgres_store import PostgresStore


router = APIRouter(prefix="/api/labels", tags=["labels"])


@router.get("")
def list_labels(store: PostgresStore = Depends(get_store)) -> ApiResponse:
    labels = store.list_label_configs()
    return ApiResponse(data=[label.model_dump(mode="json", by_alias=True) for label in labels])


@router.post("")
def create_label(request: LabelConfigCreateRequest, store: PostgresStore = Depends(get_store)) -> ApiResponse:
    try:
        label = store.create_label_config(
            english_name=request.english_name,
            chinese_name=request.chinese_name,
            description=request.description,
            copy_from_label_id=request.copy_from_label_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=409, detail="标签数据不合法") from exc
    return ApiResponse(data=label.model_dump(mode="json", by_alias=True))


@router.post("/{label_id}/copy")
def copy_label(label_id: int, store: PostgresStore = Depends(get_store)) -> ApiResponse:
    label = store.copy_label_config(label_id)
    if label is None:
        raise HTTPException(status_code=404, detail="标签不存在")
    return ApiResponse(data=label.model_dump(mode="json", by_alias=True))


@router.put("/{label_id}")
def update_label(
    label_id: int,
    request: LabelConfigUpdateRequest,
    store: PostgresStore = Depends(get_store),
) -> ApiResponse:
    try:
        label = store.update_label_config(
            label_id=label_id,
            english_name=request.english_name,
            chinese_name=request.chinese_name,
            description=request.description,
        )
    except Exception as exc:
        raise HTTPException(status_code=409, detail="标签数据不合法") from exc
    if label is None:
        raise HTTPException(status_code=404, detail="标签不存在")
    return ApiResponse(data=label.model_dump(mode="json", by_alias=True))


@router.delete("/{label_id}")
def delete_label(label_id: int, store: PostgresStore = Depends(get_store)) -> ApiResponse:
    deleted = store.delete_label_config(label_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="标签不存在")
    return ApiResponse(data={"deleted": True})
