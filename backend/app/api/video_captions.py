from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.core.dependencies import get_store
from app.models.schemas import ApiResponse, VideoCaptionBatch, VideoCaptionFrame, VideoCaptionVideo
from app.repositories.postgres_store import PostgresStore


router = APIRouter(prefix="/api/video-captions", tags=["video-captions"])


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


@router.get("/frames/{frame_id}", response_model=ApiResponse)
def get_frame(frame_id: str, store: PostgresStore = Depends(get_store)) -> ApiResponse:
    frame = store.get_video_caption_frame(frame_id)
    if frame is None:
        raise HTTPException(status_code=404, detail="video caption frame not found")
    return ApiResponse(data=_frame_payload(frame))


@router.get("/frames/{frame_id}/image")
def get_frame_image(frame_id: str, store: PostgresStore = Depends(get_store)) -> FileResponse:
    frame = store.get_video_caption_frame(frame_id)
    if frame is None:
        raise HTTPException(status_code=404, detail="video caption frame not found")
    image_path = Path(frame.image_path)
    if not image_path.exists() or not image_path.is_file():
        raise HTTPException(status_code=404, detail="video caption frame image not found")
    return FileResponse(image_path, media_type="image/jpeg")


def _batch_payload(batch: VideoCaptionBatch) -> dict:
    return {
        "batchId": batch.batch_id,
        "name": batch.name,
        "sourceDir": batch.source_dir,
        "outputDir": batch.output_dir,
        "modelId": batch.model_id,
        "prompt": batch.prompt,
        "frameIntervalSeconds": batch.frame_interval_seconds,
        "status": batch.status,
        "totalVideos": batch.total_videos,
        "totalFrames": batch.total_frames,
        "metadata": batch.metadata,
        "createdAt": batch.created_at.isoformat(),
        "updatedAt": batch.updated_at.isoformat(),
    }


def _video_payload(video: VideoCaptionVideo) -> dict:
    return {
        "videoId": video.video_id,
        "batchId": video.batch_id,
        "filename": video.filename,
        "displayName": video.display_name or video.filename,
        "keywords": video.keywords,
        "sourcePath": video.source_path,
        "frameDir": video.frame_dir,
        "fps": video.fps,
        "width": video.width,
        "height": video.height,
        "frameCount": video.frame_count,
        "durationMs": video.duration_ms,
        "status": video.status,
        "error": video.error,
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
        "imagePath": frame.image_path,
        "imageUrl": frame.image_url or f"/api/video-captions/frames/{frame.frame_id}/image",
        "width": frame.width,
        "height": frame.height,
        "descriptionText": frame.description_text,
        "modelId": frame.model_id,
        "status": frame.status,
        "error": frame.error,
        "resultJson": frame.result_json,
        "createdAt": frame.created_at.isoformat(),
        "updatedAt": frame.updated_at.isoformat(),
    }
