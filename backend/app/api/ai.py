from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_store, get_vision_service
from app.models.schemas import AiInferRequest, ApiResponse, ImageTaskResult
from app.repositories.postgres_store import PostgresStore
from app.services.vision_service import VisionService


router = APIRouter(prefix="/api/ai", tags=["image-workspace"])


@router.post("/infer", response_model=ApiResponse)
def infer_image_task(
    request: AiInferRequest,
    store: PostgresStore = Depends(get_store),
    service: VisionService = Depends(get_vision_service),
) -> ApiResponse:
    image = store.get_image_asset(request.image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="当前图片不存在")

    session_id = request.session_id or image.session_id or "default"
    task = store.create_or_get_image_task(request.image_id, request.task_type, session_id)
    store.update_image_task_status(task.task_id, "processing")

    try:
        analysis = service.analyze_path(Path(image.file_path), request.task_type, request.model_name)
        result_json = _result_from_analysis(request.task_type, analysis)
    except Exception as exc:
        store.update_image_task_status(task.task_id, "failed")
        raise HTTPException(status_code=503, detail=f"通用视觉模型执行失败: {exc}") from exc

    description = result_json.get("description", "") if isinstance(result_json, dict) else ""
    model_id = str(analysis.get("model") or request.model_name or "unknown")
    result = ImageTaskResult(
        task_id=task.task_id,
        image_id=image.image_id,
        task_type=request.task_type,
        result_image_url="",
        result_image_path="",
        result_json=result_json,
        annotation_json=_annotation_from_result(request.task_type, result_json),
        description_text=description,
        source="ai",
        model_id=model_id,
    )
    saved, version = store.save_image_task_result(result)
    return ApiResponse(
        data={
            "taskId": task.task_id,
            "imageId": image.image_id,
            "taskType": request.task_type,
            "status": "success",
            "resultId": saved.result_id,
            "versionId": version.version_id,
            "versionNo": version.version_no,
            "resultJson": result_json,
            "annotationJson": saved.annotation_json,
            "descriptionText": saved.description_text,
            "source": saved.source,
            "modelId": saved.model_id,
            "latestVersionId": version.version_id,
            "latestVersionNo": version.version_no,
        }
    )


def _result_from_analysis(task_type: str, analysis: dict) -> dict:
    if task_type == "detection":
        return {"boxes": [_box_payload(item) for item in analysis.get("objects", [])]}
    if task_type == "segmentation":
        return {
            "segments": [
                {
                    "label": item.get("label", "object"),
                    "score": float(item.get("confidence", 0.0)),
                    "polygon": item.get("polygon", []),
                }
                for item in analysis.get("segments", [])
            ]
        }
    if task_type == "pose":
        poses = analysis.get("poses", [])
        return {"keypoints": _pose_keypoints(poses), "skeleton": _pose_skeleton(poses)}
    if task_type == "classification":
        return {
            "labels": [
                {"label": item.get("label", "unknown"), "score": float(item.get("confidence", 0.0))}
                for item in analysis.get("results", [])
            ]
        }
    return {"description": str(analysis.get("caption", ""))}


def _box_payload(item: dict) -> dict:
    bbox = item.get("bbox", {})
    return {
        "x": float(bbox.get("x", 0.0)),
        "y": float(bbox.get("y", 0.0)),
        "width": float(bbox.get("width", 1.0)),
        "height": float(bbox.get("height", 1.0)),
        "label": str(item.get("label", "object")),
        "score": float(item.get("confidence", 0.0)),
    }


KEYPOINT_NAMES = [
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
]

COCO_SKELETON = [
    ("left_shoulder", "right_shoulder"),
    ("left_shoulder", "left_elbow"),
    ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"),
    ("right_elbow", "right_wrist"),
    ("left_shoulder", "left_hip"),
    ("right_shoulder", "right_hip"),
    ("left_hip", "right_hip"),
    ("left_hip", "left_knee"),
    ("left_knee", "left_ankle"),
    ("right_hip", "right_knee"),
    ("right_knee", "right_ankle"),
    ("nose", "left_eye"),
    ("nose", "right_eye"),
    ("left_eye", "left_ear"),
    ("right_eye", "right_ear"),
]


def _pose_keypoints(poses: list[dict]) -> list[dict]:
    keypoints: list[dict] = []
    for pose_index, pose in enumerate(poses):
        coordinates = pose.get("keypoints", [])
        confidences = pose.get("confidence", [])
        for point_index, coordinates_xy in enumerate(coordinates):
            if len(coordinates_xy) < 2:
                continue
            base_name = KEYPOINT_NAMES[point_index] if point_index < len(KEYPOINT_NAMES) else f"point_{point_index}"
            keypoints.append(
                {
                    "name": f"person_{pose_index}_{base_name}",
                    "x": float(coordinates_xy[0]),
                    "y": float(coordinates_xy[1]),
                    "score": float(confidences[point_index]) if point_index < len(confidences) else 0.0,
                }
            )
    return keypoints


def _pose_skeleton(poses: list[dict]) -> list[dict]:
    skeleton: list[dict] = []
    for pose_index, pose in enumerate(poses):
        coordinates = pose.get("keypoints", [])
        confidences = pose.get("confidence", [])
        points: dict[str, dict] = {}
        for point_index, coordinates_xy in enumerate(coordinates):
            if len(coordinates_xy) < 2 or point_index >= len(KEYPOINT_NAMES):
                continue
            score = float(confidences[point_index]) if point_index < len(confidences) else 1.0
            if score <= 0.05:
                continue
            x = float(coordinates_xy[0])
            y = float(coordinates_xy[1])
            if x <= 0 and y <= 0:
                continue
            points[KEYPOINT_NAMES[point_index]] = {"x": x, "y": y, "score": score}

        for start_name, end_name in COCO_SKELETON:
            start = points.get(start_name)
            end = points.get(end_name)
            if not start or not end:
                continue
            skeleton.append(
                {
                    "name": f"person_{pose_index}_{start_name}_to_{end_name}",
                    "from": f"person_{pose_index}_{start_name}",
                    "to": f"person_{pose_index}_{end_name}",
                    "x1": start["x"],
                    "y1": start["y"],
                    "x2": end["x"],
                    "y2": end["y"],
                    "score": min(start["score"], end["score"]),
                }
            )
    return skeleton


def _annotation_from_result(task_type: str, result_json: dict) -> dict:
    if task_type == "detection":
        return {"shapes": result_json.get("boxes", [])}
    if task_type == "segmentation":
        return {"shapes": result_json.get("segments", [])}
    if task_type == "pose":
        return {"keypoints": result_json.get("keypoints", []), "skeleton": result_json.get("skeleton", [])}
    if task_type == "classification":
        return {"labels": result_json.get("labels", [])}
    return {"description": result_json.get("description", "")}
