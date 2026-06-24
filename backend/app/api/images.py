import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from PIL import Image

from app.core.config import Settings, get_settings
from app.core.dependencies import get_store
from app.models.schemas import ApiResponse, ImageAsset, ImageHistoryResponse, ImageTaskType, now_utc
from app.repositories.postgres_store import PostgresStore


router = APIRouter(prefix="/api/images", tags=["image-workspace"])

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024


@router.post("/upload", response_model=ApiResponse)
def upload_image(
    file: UploadFile = File(...),
    task_type: ImageTaskType = Form(..., alias="taskType"),
    session_id: str = Form(default="default", alias="sessionId"),
    settings: Settings = Depends(get_settings),
    store: PostgresStore = Depends(get_store),
) -> ApiResponse:
    del task_type
    original_name = Path(file.filename or "upload.png").name
    extension = Path(original_name).suffix.lower()
    if extension not in SUPPORTED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="图片格式不支持，请上传 jpg、jpeg、png、webp 或 bmp")

    current = now_utc()
    target_dir = settings.upload_dir / "images" / "original" / f"{current.year:04d}" / f"{current.month:02d}"
    target_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{uuid4().hex}{extension}"
    target_path = target_dir / file_name

    with target_path.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)

    file_size = target_path.stat().st_size
    if file_size > MAX_IMAGE_BYTES:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="图片大小超过 20MB 限制")

    try:
        with Image.open(target_path) as image:
            width, height = image.size
            image.verify()
    except Exception as exc:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="图片文件无法解析") from exc

    relative_url = "/" + target_path.relative_to(settings.data_dir).as_posix()
    image_asset = ImageAsset(
        original_name=original_name,
        file_name=file_name,
        file_url=relative_url,
        file_path=str(target_path),
        mime_type=file.content_type or "application/octet-stream",
        file_size=file_size,
        width=width,
        height=height,
        session_id=session_id or "default",
    )
    store.create_image_asset(image_asset)
    return ApiResponse(data=_image_payload(image_asset))


@router.get("/list", response_model=ApiResponse)
def list_images(
    task_type: ImageTaskType | None = Query(default=None, alias="taskType"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200, alias="pageSize"),
    session_id: str = Query(default="default", alias="sessionId"),
    store: PostgresStore = Depends(get_store),
) -> ApiResponse:
    records, total = store.list_image_assets(task_type, session_id or "default", page, page_size)
    data = ImageHistoryResponse(records=records, total=total)
    return ApiResponse(data={"records": [_image_payload(record) for record in data.records], "total": data.total})


def _image_payload(image: ImageAsset) -> dict:
    return {
        "imageId": image.image_id,
        "imageUrl": image.file_url,
        "originalName": image.original_name,
        "fileName": image.file_name,
        "fileUrl": image.file_url,
        "filePath": image.file_path,
        "mimeType": image.mime_type,
        "fileSize": image.file_size,
        "width": image.width,
        "height": image.height,
        "sessionId": image.session_id,
        "createdAt": image.created_at.isoformat(),
        "updatedAt": image.updated_at.isoformat(),
        "hasCurrentTaskResult": image.has_current_task_result,
        "taskStatus": image.task_status,
    }
