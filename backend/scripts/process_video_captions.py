import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.dependencies import get_store, get_vision_service
from app.models.schemas import VideoCaptionBatch, VideoCaptionFrame, VideoCaptionVideo, new_id, now_utc


DEFAULT_SOURCE_DIR = Path("/ds2/videos/DJI_001")
DEFAULT_MODEL_ID = "deepseek-ai/deepseek-vl2-tiny"
DEFAULT_PROMPT = "请用中文描述画面，列出可见的铁路目标、人员、车辆、轨道、设备、施工场景或安全风险。"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract video frames, caption them with local DeepSeek-VL2, and save results to DB.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--batch-name", default="")
    parser.add_argument("--frame-interval-seconds", type=float, default=1.0)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--limit-videos", type=int, default=None)
    parser.add_argument("--max-frames-per-video", type=int, default=None)
    parser.add_argument("--force", action="store_true", help="Re-caption frames that already have successful results.")
    parser.add_argument("--min-free-mib", type=int, default=9000, help="Free VRAM required before captioning starts.")
    parser.add_argument(
        "--wait-for-vram",
        action="store_true",
        help="Block until --min-free-mib is available instead of exiting (for shared GPU hosts).",
    )
    args = parser.parse_args()

    if args.frame_interval_seconds <= 0:
        raise SystemExit("--frame-interval-seconds must be greater than 0")
    if not args.source_dir.exists():
        raise SystemExit(f"source directory not found: {args.source_dir}")

    free_mib = _free_vram_mib()
    if free_mib is not None and free_mib < args.min_free_mib:
        if not args.wait_for_vram:
            raise SystemExit(
                f"only {free_mib} MiB of VRAM free, need {args.min_free_mib} MiB. "
                "Free the GPU (ollama stop <model>) or pass --wait-for-vram."
            )
        _wait_for_vram(args.min_free_mib)

    settings = get_settings()
    store = get_store()
    service = get_vision_service()
    service.settings.deepseek_vl2_prompt = args.prompt

    source_dir = args.source_dir.resolve()
    batch_name = args.batch_name.strip() or source_dir.name
    output_dir = settings.data_dir / "video_captions" / _slug(batch_name)
    output_dir.mkdir(parents=True, exist_ok=True)

    batch = store.create_or_update_video_caption_batch(
        VideoCaptionBatch(
            name=batch_name,
            source_dir=str(source_dir),
            output_dir=str(output_dir),
            model_id=args.model_id,
            prompt=args.prompt,
            frame_interval_seconds=args.frame_interval_seconds,
            status="processing",
        )
    )

    video_paths = sorted(path for path in source_dir.iterdir() if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS)
    if args.limit_videos is not None:
        video_paths = video_paths[: args.limit_videos]

    print(f"Batch {batch.name}: {len(video_paths)} video(s), interval={args.frame_interval_seconds}s", flush=True)
    try:
        for position, video_path in enumerate(video_paths, start=1):
            print(f"[{position}/{len(video_paths)}] {video_path.name}", flush=True)
            _process_video(
                video_path=video_path,
                batch=batch,
                output_dir=output_dir,
                frame_interval_seconds=args.frame_interval_seconds,
                model_id=args.model_id,
                store=store,
                service=service,
                max_frames=args.max_frames_per_video,
                force=args.force,
                min_free_mib=args.min_free_mib,
            )
        store.update_video_caption_batch_counts(batch.batch_id, status="success")
        print(f"Batch {batch.name} finished", flush=True)
    finally:
        # Release VL2 VRAM: the translation stage needs the card for ollama.
        service.unload_models()
        print("Vision models unloaded", flush=True)


def _process_video(
    video_path: Path,
    batch: VideoCaptionBatch,
    output_dir: Path,
    frame_interval_seconds: float,
    model_id: str,
    store,
    service,
    max_frames: int | None,
    force: bool,
    min_free_mib: int,
) -> None:
    try:
        import cv2
    except Exception as exc:
        raise RuntimeError("opencv-python-headless is required for video frame extraction") from exc

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        video = VideoCaptionVideo(
            batch_id=batch.batch_id,
            filename=video_path.name,
            source_path=str(video_path),
            status="failed",
            error="could not open video",
        )
        store.create_or_update_video_caption_video(video)
        return

    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0) or None
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0) or None
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0) or None
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0) or None
    duration_ms = int(frame_count / fps * 1000) if fps and frame_count else None
    frame_dir = output_dir / video_path.stem / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)

    video = store.create_or_update_video_caption_video(
        VideoCaptionVideo(
            batch_id=batch.batch_id,
            filename=video_path.name,
            source_path=str(video_path),
            frame_dir=str(frame_dir),
            fps=fps,
            width=width,
            height=height,
            frame_count=frame_count,
            duration_ms=duration_ms,
            status="processing",
        )
    )

    step = max(1, int(round((fps or 1.0) * frame_interval_seconds)))
    target_indexes = range(0, frame_count or 0, step) if frame_count else _unknown_frame_indexes(capture, step)
    processed = 0
    succeeded = 0

    try:
        for frame_index in target_indexes:
            if max_frames is not None and processed >= max_frames:
                break

            existing = store.get_video_caption_frame_by_index(video.video_id, frame_index)
            if existing and existing.status == "success" and not force:
                processed += 1
                succeeded += 1
                continue

            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok:
                continue

            timestamp_ms = int(frame_index / fps * 1000) if fps else 0
            image_path = frame_dir / f"frame_{frame_index:06d}_{timestamp_ms:010d}.jpg"
            cv2.imwrite(str(image_path), frame)
            frame_height, frame_width = frame.shape[:2]
            record = VideoCaptionFrame(
                frame_id=existing.frame_id if existing else new_id("vcframe"),
                batch_id=batch.batch_id,
                video_id=video.video_id,
                frame_index=frame_index,
                timestamp_ms=timestamp_ms,
                image_path=str(image_path),
                width=int(frame_width),
                height=int(frame_height),
                model_id=model_id,
                status="processing",
            )
            record.image_url = f"/api/video-captions/frames/{record.frame_id}/image"

            try:
                description = _caption_with_retry(service, image_path, min_free_mib)
                record.description_text = description
                record.status = "success"
                succeeded += 1
                record.result_json = {
                    "description": description,
                    "model": model_id,
                    "video": video_path.name,
                    "frameIndex": frame_index,
                    "timestampMs": timestamp_ms,
                }
            except Exception as exc:
                record.status = "failed"
                record.error = str(exc)
            store.save_video_caption_frame(record)
            processed += 1
            print(
                f"  frame={frame_index} status={record.status} timestamp_ms={timestamp_ms}",
                flush=True,
            )
    finally:
        capture.release()

    saved_status = "success" if succeeded > 0 else "failed"
    saved_error = "" if succeeded > 0 else "no successful frame captions"
    store.create_or_update_video_caption_video(
        VideoCaptionVideo(
            video_id=video.video_id,
            batch_id=batch.batch_id,
            filename=video.filename,
            source_path=video.source_path,
            frame_dir=video.frame_dir,
            fps=video.fps,
            width=video.width,
            height=video.height,
            frame_count=video.frame_count,
            duration_ms=video.duration_ms,
            status=saved_status,
            error=saved_error,
            created_at=video.created_at,
            updated_at=now_utc(),
        )
    )
    store.update_video_caption_batch_counts(batch.batch_id, status="processing")


def _caption_with_retry(service, image_path: Path, min_free_mib: int, attempts: int = 3) -> str:
    """Caption one frame, reclaiming VRAM and retrying if the GPU was taken mid-run.

    This box is shared with other GPU services, so a frame can hit an allocation
    failure even though the run started with enough free memory.
    """
    for attempt in range(1, attempts + 1):
        try:
            return service._deepseek_vl2_caption(image_path)
        except Exception as exc:
            if attempt == attempts or "out of memory" not in str(exc).lower():
                raise
            print(f"    CUDA OOM (attempt {attempt}/{attempts}); dropping models and waiting for VRAM", flush=True)
            service.unload_models()
            _wait_for_vram(min_free_mib)
    raise RuntimeError("unreachable")


def _free_vram_mib() -> int | None:
    try:
        output = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        ).stdout
    except Exception:
        return None
    first = output.strip().splitlines()[0].strip() if output.strip() else ""
    return int(first) if first.isdigit() else None


def _wait_for_vram(min_free_mib: int, poll_seconds: int = 30) -> None:
    while True:
        free_mib = _free_vram_mib()
        if free_mib is None:
            print("  nvidia-smi unavailable; assuming the GPU is usable", flush=True)
            return
        if free_mib >= min_free_mib:
            print(f"  {free_mib} MiB free VRAM, resuming", flush=True)
            return
        print(f"  waiting for VRAM: {free_mib} MiB free, need {min_free_mib} MiB", flush=True)
        time.sleep(poll_seconds)


def _unknown_frame_indexes(capture, step: int):
    frame_index = 0
    while True:
        ok = capture.grab()
        if not ok:
            break
        if frame_index % step == 0:
            yield frame_index
        frame_index += 1


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return slug or "video-captions"


if __name__ == "__main__":
    main()
