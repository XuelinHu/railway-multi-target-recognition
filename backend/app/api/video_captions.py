from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
import httpx

from app.api.auth import require_user
from app.core.config import Settings, get_settings
from app.core.dependencies import get_store
from app.models.schemas import ApiResponse, AuthUser, VideoCaptionBatch, VideoCaptionFrame, VideoCaptionFrameReviewUpdateRequest, VideoCaptionVideo
from app.repositories.postgres_store import PostgresStore


router = APIRouter(prefix="/api/video-captions", tags=["video-captions"])


@router.get("/models", response_model=ApiResponse)
def list_local_models(settings: Settings = Depends(get_settings)) -> ApiResponse:
    task_suffixes = {
        "detection": (".pt", ".engine"),
        "segmentation": (".pt",),
        "pose": (".pt",),
        "classification": (".pt",),
        "caption": ("config.json",),
    }
    found: dict[str, list[str]] = {key: [] for key in task_suffixes}
    for root_text in settings.model_search_dirs.split(","):
        root = Path(root_text.strip()).expanduser()
        if not root.is_dir():
            continue
        scan = root.glob("*") if root.name == "backend" else root.rglob("*")
        for path in scan:
            if not path.is_file():
                continue
            name = path.name.lower()
            relative = path.name
            if name.endswith((".pt", ".engine")):
                if "-seg" in name:
                    task = "segmentation"
                elif "-pose" in name:
                    task = "pose"
                elif "-cls" in name:
                    task = "classification"
                elif name.endswith((".pt", ".engine")):
                    task = "detection"
                model_id = path.stem
                if model_id not in found[task]:
                    found[task].append(model_id)
            if name == "config.json" and any(token in path.as_posix().lower() for token in ("deepseek-vl2", "blip")):
                model = path.parent.name
                if model not in found["caption"]:
                    found["caption"].append(model)
    return ApiResponse(data=found)


@router.get("/batches", response_model=ApiResponse)
def list_batches(store: PostgresStore = Depends(get_store)) -> ApiResponse:
    return ApiResponse(data=[_batch_payload(batch) for batch in store.list_video_caption_batches()])


@router.get("/batches/{batch_id}", response_model=ApiResponse)
def get_batch(batch_id: str, store: PostgresStore = Depends(get_store)) -> ApiResponse:
    batch = store.get_video_caption_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="video caption batch not found")
    return ApiResponse(data=_batch_payload(batch))


@router.get("/batches/{batch_id}/videos", response_model=ApiResponse)
def list_videos(batch_id: str, store: PostgresStore = Depends(get_store)) -> ApiResponse:
    if store.get_video_caption_batch(batch_id) is None:
        raise HTTPException(status_code=404, detail="video caption batch not found")
    return ApiResponse(data=[_video_payload(video) for video in store.list_video_caption_videos(batch_id)])


@router.get("/videos/{video_id}/frames", response_model=ApiResponse)
def list_frames(
    video_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500, alias="pageSize"),
    query: str = Query(default=""),
    store: PostgresStore = Depends(get_store),
) -> ApiResponse:
    if store.get_video_caption_video(video_id) is None:
        raise HTTPException(status_code=404, detail="video caption video not found")
    frames, total = store.list_video_caption_frames(video_id, page=page, page_size=page_size, query=query.strip())
    return ApiResponse(data={"records": [_frame_payload(frame) for frame in frames], "total": total})


@router.get("/videos/{video_id}/source")
def get_video_source(video_id: str, store: PostgresStore = Depends(get_store)) -> FileResponse:
    video = store.get_video_caption_video(video_id)
    if video is None or not Path(video.source_path).is_file():
        raise HTTPException(status_code=404, detail="video source not found")
    return FileResponse(video.source_path, media_type="video/mp4", filename=video.filename)


@router.get("/videos/{video_id}/pose-source")
def get_video_pose_source(video_id: str, store: PostgresStore = Depends(get_store)) -> FileResponse:
    video = store.get_video_caption_video(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="video caption video not found")
    source_path = Path(video.source_path)
    pose_path = source_path.parent / "pose_outputs" / f"{source_path.stem}_pose.mp4"
    if not pose_path.is_file():
        raise HTTPException(status_code=404, detail="pose video not found")
    return FileResponse(pose_path, media_type="video/mp4", filename=pose_path.name)


@router.get("/frames/{frame_id}", response_model=ApiResponse)
def get_frame(frame_id: str, store: PostgresStore = Depends(get_store)) -> ApiResponse:
    frame = store.get_video_caption_frame(frame_id)
    if frame is None:
        raise HTTPException(status_code=404, detail="video caption frame not found")
    return ApiResponse(data=_frame_payload(frame))


@router.put("/frames/{frame_id}/review", response_model=ApiResponse)
def update_frame_review(
    frame_id: str,
    request: VideoCaptionFrameReviewUpdateRequest,
    store: PostgresStore = Depends(get_store),
    current_user: AuthUser = Depends(require_user),
) -> ApiResponse:
    if current_user.role == "reviewer":
        raise HTTPException(status_code=403, detail="审核员不能编辑视频描述")
    frame = store.update_video_caption_frame_review(frame_id, request.description_manual, request.safety_score)
    if frame is None:
        raise HTTPException(status_code=404, detail="视频帧不存在")
    return ApiResponse(data=_frame_payload(frame))


@router.post("/frames/{frame_id}/translate", response_model=ApiResponse)
def translate_frame_description(
    frame_id: str,
    settings: Settings = Depends(get_settings),
    store: PostgresStore = Depends(get_store),
    current_user: AuthUser = Depends(require_user),
) -> ApiResponse:
    if current_user.role == "reviewer":
        raise HTTPException(status_code=403, detail="审核员不能生成或修改描述")
    frame = store.get_video_caption_frame(frame_id)
    if frame is None:
        raise HTTPException(status_code=404, detail="视频帧不存在")
    if not frame.description_text.strip():
        raise HTTPException(status_code=409, detail="中文描述为空，无法生成英文翻译")
    try:
        tags = httpx.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags", timeout=8)
        tags.raise_for_status()
        available = {item.get("name") for item in tags.json().get("models", [])}
        model = settings.ollama_default_model if settings.ollama_default_model in available else "qwen3:4b"
        response = httpx.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/chat",
            json={
                "model": model,
                "stream": False,
                "think": False,
                "messages": [
                    {"role": "system", "content": "Translate the Chinese railway image caption into concise English. Return only the translation."},
                    {"role": "user", "content": frame.description_text},
                ],
                "options": {"temperature": 0.1},
            },
            timeout=120,
        )
        response.raise_for_status()
        translated = str((response.json().get("message") or {}).get("content") or "").strip()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"本地模型翻译失败：{type(exc).__name__}") from exc
    if not translated:
        raise HTTPException(status_code=502, detail="本地模型没有返回英文描述")
    updated = store.update_video_caption_frame_translation(frame_id, translated)
    return ApiResponse(data=_frame_payload(updated))


@router.get("/frames/{frame_id}/image")
def get_frame_image(
    frame_id: str,
    settings: Settings = Depends(get_settings),
    store: PostgresStore = Depends(get_store),
) -> FileResponse:
    frame = store.get_video_caption_frame(frame_id)
    if frame is None:
        raise HTTPException(status_code=404, detail="video caption frame not found")
    image_path = Path(frame.image_path)
    if not image_path.is_absolute():
        image_path = settings.data_dir / image_path
    if not image_path.is_file():
        try:
            image_path = settings.legacy_data_dir / Path(frame.image_path).relative_to(settings.legacy_data_dir)
        except ValueError:
            pass
    if not image_path.exists() or not image_path.is_file():
        raise HTTPException(status_code=404, detail="video caption frame image not found")
    return FileResponse(image_path, media_type="image/jpeg")


def _batch_payload(batch: VideoCaptionBatch) -> dict:
    return {
        "batchId": batch.batch_id,
        "name": batch.name,
        "modelId": batch.model_id,
        "frameIntervalSeconds": batch.frame_interval_seconds,
        "status": batch.status,
        "totalVideos": batch.total_videos,
        "totalFrames": batch.total_frames,
        "createdAt": batch.created_at.isoformat(),
        "updatedAt": batch.updated_at.isoformat(),
    }


def _video_payload(video: VideoCaptionVideo) -> dict:
    source_path = Path(video.source_path)
    pose_path = source_path.parent / "pose_outputs" / f"{source_path.stem}_pose.mp4"
    return {
        "videoId": video.video_id,
        "batchId": video.batch_id,
        "filename": video.filename,
        "displayName": video.display_name or video.filename,
        "sourceUrl": f"/api/video-captions/videos/{video.video_id}/source",
        "poseUrl": f"/api/video-captions/videos/{video.video_id}/pose-source" if pose_path.is_file() else None,
        "keywords": video.keywords,
        "durationMs": video.duration_ms,
        "similarFramesSkipped": video.similar_frames_skipped,
        "status": video.status,
        "createdAt": video.created_at.isoformat(),
        "updatedAt": video.updated_at.isoformat(),
    }


def _frame_payload(frame: VideoCaptionFrame) -> dict:
    return {
        "frameId": frame.frame_id,
        "batchId": frame.batch_id,
        "videoId": frame.video_id,
        "frameIndex": frame.frame_index,
        "timestampMs": frame.timestamp_ms,
        "imageUrl": frame.image_url or f"/api/video-captions/frames/{frame.frame_id}/image",
        "descriptionText": frame.description_text,
        "descriptionEn": frame.description_en,
        "descriptionManual": frame.description_manual,
        "safetyScore": frame.safety_score,
        "modelId": frame.model_id,
        "status": frame.status,
        "width": frame.width,
        "height": frame.height,
        "resultJson": frame.result_json,
        "createdAt": frame.created_at.isoformat(),
        "updatedAt": frame.updated_at.isoformat(),
    }
