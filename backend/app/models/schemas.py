from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


AssetType = Literal["image", "video", "unknown"]
TaskStatus = Literal["queued", "running", "completed", "failed"]
ObjectStatus = Literal["auto", "confirmed", "edited", "rejected"]
ObjectSource = Literal["auto", "manual"]
ReviewStatus = Literal["pending_review", "in_review", "approved", "rejected"]
ImageTaskType = Literal["detection", "segmentation", "pose", "classification", "caption"]
ImageTaskStatus = Literal["idle", "pending", "processing", "success", "failed"]
ResultSource = Literal["ai", "manual", "edited"]


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class BBox(BaseModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class DetectionObject(BaseModel):
    id: str = Field(default_factory=lambda: new_id("obj"))
    label: str
    confidence: float = Field(ge=0, le=1)
    bbox: BBox
    track_id: int | None = None
    source: ObjectSource = "auto"
    status: ObjectStatus = "auto"


class AnnotationFrame(BaseModel):
    frame_index: int = Field(ge=0)
    timestamp_ms: int = Field(ge=0)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    image_url: str | None = None
    review_status: ReviewStatus = "pending_review"
    objects: list[DetectionObject] = Field(default_factory=list)


class AnnotationsDocument(BaseModel):
    asset_id: str
    type: AssetType
    model: str
    review_status: ReviewStatus = "pending_review"
    frames: list[AnnotationFrame] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=now_utc)
    reviewed_at: datetime | None = None


class Asset(BaseModel):
    id: str = Field(default_factory=lambda: new_id("asset"))
    filename: str
    content_type: str
    type: AssetType = "unknown"
    path: str
    size_bytes: int = Field(ge=0)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    frame_count: int | None = Field(default=None, ge=1)
    duration_ms: int | None = Field(default=None, ge=0)
    fps: float | None = Field(default=None, gt=0)
    created_at: datetime = Field(default_factory=now_utc)


class DetectionRequest(BaseModel):
    asset_id: str
    confidence: float = Field(default=0.25, ge=0, le=1)
    iou: float = Field(default=0.7, ge=0, le=1)
    frame_stride: int = Field(default=1, ge=1)
    max_frames: int | None = Field(default=None, ge=1)
    model_name: str | None = None


class ReviewRequest(BaseModel):
    status: ReviewStatus


class DetectTask(BaseModel):
    id: str = Field(default_factory=lambda: new_id("task"))
    asset_id: str
    status: TaskStatus = "queued"
    progress: float = Field(default=0, ge=0, le=1)
    model_name: str = "mock"
    params: DetectionRequest
    error: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ImageAsset(BaseModel):
    image_id: str = Field(default_factory=lambda: new_id("img"))
    original_name: str
    file_name: str
    file_url: str
    file_path: str
    mime_type: str | None = None
    file_size: int = Field(ge=0)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    user_id: str | None = None
    session_id: str = "default"
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
    has_current_task_result: bool = False
    task_status: ImageTaskStatus = "idle"


class ImageHistoryResponse(BaseModel):
    records: list[ImageAsset]
    total: int


class ImageTask(BaseModel):
    task_id: str = Field(default_factory=lambda: new_id("itask"))
    image_id: str
    task_type: ImageTaskType
    status: ImageTaskStatus = "pending"
    user_id: str | None = None
    session_id: str = "default"
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class ImageTaskCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    image_id: str = Field(alias="imageId")
    task_type: ImageTaskType = Field(alias="taskType")
    session_id: str | None = Field(default=None, alias="sessionId")
    user_id: str | None = Field(default=None, alias="userId")


class ImageTaskResult(BaseModel):
    result_id: str = Field(default_factory=lambda: new_id("ires"))
    task_id: str
    image_id: str
    task_type: ImageTaskType
    status: ImageTaskStatus = "success"
    result_image_url: str = ""
    result_image_path: str = ""
    result_json: dict[str, Any] | None = None
    annotation_json: dict[str, Any] | None = None
    description_text: str = ""
    source: ResultSource = "edited"
    model_id: str = ""
    latest_version_id: str | None = None
    latest_version_no: int | None = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class ImageTaskResultSaveRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_id: str = Field(alias="taskId")
    image_id: str = Field(alias="imageId")
    task_type: ImageTaskType = Field(alias="taskType")
    result_image_url: str = Field(default="", alias="resultImageUrl")
    result_image_path: str = Field(default="", alias="resultImagePath")
    result_json: dict[str, Any] | None = Field(default=None, alias="resultJson")
    annotation_json: dict[str, Any] | None = Field(default=None, alias="annotationJson")
    description_text: str = Field(default="", alias="descriptionText")
    source: ResultSource = "edited"
    model_id: str = Field(default="", alias="modelId")


class ImageTaskResultVersion(BaseModel):
    version_id: str = Field(default_factory=lambda: new_id("iver"))
    result_id: str
    task_id: str
    image_id: str
    task_type: ImageTaskType
    version_no: int = Field(ge=1)
    source: ResultSource = "edited"
    model_id: str = ""
    result_image_url: str = ""
    result_image_path: str = ""
    result_json: dict[str, Any] | None = None
    annotation_json: dict[str, Any] | None = None
    description_text: str = ""
    created_at: datetime = Field(default_factory=now_utc)


class ImageTaskAnnotationUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_id: str = Field(alias="taskId")
    image_id: str = Field(alias="imageId")
    task_type: ImageTaskType = Field(alias="taskType")
    annotation_json: dict[str, Any] = Field(alias="annotationJson")


class AiInferRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    image_id: str = Field(alias="imageId")
    task_type: ImageTaskType = Field(alias="taskType")
    model_name: str | None = Field(default=None, alias="modelName")
    session_id: str | None = Field(default=None, alias="sessionId")


class LabelConfig(BaseModel):
    label_id: int = Field(ge=0, alias="labelId")
    english_name: str = Field(min_length=1, max_length=120, alias="englishName")
    chinese_name: str = Field(min_length=1, max_length=120, alias="chineseName")
    description: str = ""
    created_at: datetime = Field(default_factory=now_utc, alias="createdAt")
    updated_at: datetime = Field(default_factory=now_utc, alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True)


class LabelConfigCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    english_name: str = Field(min_length=1, max_length=120, alias="englishName")
    chinese_name: str = Field(min_length=1, max_length=120, alias="chineseName")
    description: str = ""
    copy_from_label_id: int | None = Field(default=None, ge=0, alias="copyFromLabelId")


class LabelConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    english_name: str = Field(min_length=1, max_length=120, alias="englishName")
    chinese_name: str = Field(min_length=1, max_length=120, alias="chineseName")
    description: str = ""


class ApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: Any = None


class ErrorResponse(BaseModel):
    detail: str
