from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


AssetType = Literal["image", "video", "unknown"]
TaskStatus = Literal["queued", "running", "completed", "failed"]
ObjectStatus = Literal["auto", "confirmed", "edited", "rejected"]
ObjectSource = Literal["auto", "manual"]
ReviewStatus = Literal["pending_review", "in_review", "approved", "rejected"]


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
    type: AssetType
    path: str
    size_bytes: int
    width: int | None = None
    height: int | None = None
    frame_count: int | None = None
    duration_ms: int | None = None
    fps: float | None = None
    created_at: datetime = Field(default_factory=now_utc)


class DetectionRequest(BaseModel):
    asset_id: str
    confidence: float = Field(default=0.25, ge=0, le=1)
    iou: float = Field(default=0.7, ge=0, le=1)
    frame_stride: int = Field(default=1, ge=1)
    max_frames: int | None = Field(default=None, ge=1)


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


class ErrorResponse(BaseModel):
    detail: str
