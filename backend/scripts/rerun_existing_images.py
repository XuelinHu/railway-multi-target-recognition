from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.ai import _annotation_from_result, _result_from_analysis
from app.core.config import get_settings
from app.core.dependencies import get_store
from app.models.schemas import ImageTaskResult


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-run a local YOLO model on all saved video-frame images.")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--task-type", default="detection", choices=["detection", "segmentation", "pose"])
    parser.add_argument("--device", default="0")
    args = parser.parse_args()
    from ultralytics import YOLO

    model = YOLO(str(args.model))
    store = get_store()
    frames = []
    for batch in store.list_video_caption_batches():
        for video in store.list_video_caption_videos(batch.batch_id):
            records, _ = store.list_video_caption_frames(video.video_id, page=1, page_size=100000)
            frames.extend(records)
    print(f"frames={len(frames)} model={args.model_id}", flush=True)
    done = 0
    for frame in frames:
        image_path = Path(frame.image_path)
        if not image_path.is_file():
            print(f"SKIP missing={frame.frame_id}", flush=True)
            continue
        analysis = _analysis(model, image_path, args.device)
        result_json = _result_from_analysis(args.task_type, analysis)
        task = store.create_or_get_image_task(frame.frame_id, args.task_type, f"video-import:{frame.video_id}", None)
        store.save_image_task_result(ImageTaskResult(
            task_id=task.task_id,
            image_id=frame.frame_id,
            task_type=args.task_type,
            result_json=result_json,
            annotation_json=_annotation_from_result(args.task_type, result_json),
            source="ai",
            model_id=args.model_id,
        ))
        store.update_image_task_status(task.task_id, "success")
        done += 1
        if done % 25 == 0:
            print(f"progress={done}/{len(frames)}", flush=True)
    print(f"finished={done}/{len(frames)}", flush=True)


def _analysis(model, image_path: Path, device: str) -> dict:
    result = model.predict(str(image_path), device=device, verbose=False)[0]
    names = result.names
    objects = []
    if result.boxes is not None:
        for box, confidence, class_id in zip(result.boxes.xyxy.cpu().tolist(), result.boxes.conf.cpu().tolist(), result.boxes.cls.cpu().tolist()):
            x1, y1, x2, y2 = box
            objects.append({"label": str(names[int(class_id)]), "confidence": float(confidence), "bbox": {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}})
    height, width = result.orig_shape[:2]
    return {"feature": "detection", "model": "yolo26s", "image": {"width": width, "height": height}, "objects": objects}


if __name__ == "__main__":
    main()
