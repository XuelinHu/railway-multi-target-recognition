from pathlib import Path
from typing import Any

from PIL import Image

from app.core.config import Settings
from app.models.schemas import (
    AnnotationFrame,
    AnnotationsDocument,
    Asset,
    BBox,
    DetectionObject,
    DetectionRequest,
)
from app.services.storage_service import FrameSource, StorageService

MODEL_ALIASES = {
    "railway-yolo-default": "yolo11n.pt",
    "custom-railway-detector": "yolo11n.pt",
    "yolov8n": "yolov8n.pt",
    "yolo11n": "yolo11n.pt",
    "yolo11n-seg": "yolo11n-seg.pt",
    "railway-seg-light": "yolo11n-seg.pt",
    "custom-segmentation": "yolo11n-seg.pt",
    "yolo11n-pose": "yolo11n-pose.pt",
    "railway-worker-pose": "yolo11n-pose.pt",
    "custom-pose": "yolo11n-pose.pt",
    "yolo11n-cls": "yolo11n-cls.pt",
    "railway-scene-cls": "yolo11n-cls.pt",
}


class InferenceService:
    def __init__(self, settings: Settings, storage: StorageService) -> None:
        self.settings = settings
        self.storage = storage
        self._models: dict[str, Any] = {}

    @property
    def model_name(self) -> str:
        if self.settings.inference_backend in {"ultralytics", "tensorrt"}:
            return Path(self.settings.model_path).name if self.settings.model_path else "yolo11n.pt"
        return "mock"

    def predict(self, asset: Asset, request: DetectionRequest) -> AnnotationsDocument:
        frames = self.storage.extract_frames(
            asset,
            frame_stride=request.frame_stride,
            max_frames=request.max_frames,
        )
        if self.settings.inference_backend in {"ultralytics", "tensorrt"}:
            return self._predict_ultralytics(asset, request, frames)
        return self._predict_mock(asset, frames)

    def _predict_mock(self, asset: Asset, frames: list[FrameSource]) -> AnnotationsDocument:
        annotation_frames: list[AnnotationFrame] = []
        for frame_source in frames:
            width = frame_source.width
            height = frame_source.height
            bbox = BBox(
                x=round(width * 0.35, 2),
                y=round(height * 0.28, 2),
                width=round(width * 0.3, 2),
                height=round(height * 0.42, 2),
            )
            annotation_frames.append(
                AnnotationFrame(
                    frame_index=frame_source.frame_index,
                    timestamp_ms=frame_source.timestamp_ms,
                    width=width,
                    height=height,
                    image_url=frame_source.image_url,
                    objects=[
                        DetectionObject(
                            label="railway_target",
                            confidence=0.88,
                            bbox=bbox,
                        )
                    ],
                )
            )
        return AnnotationsDocument(asset_id=asset.id, type=asset.type, model="mock", frames=annotation_frames)

    def _predict_ultralytics(
        self,
        asset: Asset,
        request: DetectionRequest,
        frames: list[FrameSource],
    ) -> AnnotationsDocument:
        model_path = self._resolve_model_path(request.model_name)
        model = self._load_ultralytics_model(model_path)
        annotation_frames: list[AnnotationFrame] = []

        for frame_source in frames:
            results = model(
                str(frame_source.path),
                conf=request.confidence,
                iou=request.iou,
                device=self._device(),
                verbose=False,
            )
            result = results[0]
            height, width = self._result_shape(result, asset, frame_source)
            names = getattr(result, "names", {}) or {}
            objects: list[DetectionObject] = []

            for box in result.boxes or []:
                xyxy = box.xyxy[0].tolist()
                class_id = int(box.cls[0].item()) if box.cls is not None else -1
                confidence = float(box.conf[0].item()) if box.conf is not None else 0.0
                track_id = int(box.id[0].item()) if getattr(box, "id", None) is not None else None
                objects.append(
                    DetectionObject(
                        label=str(names.get(class_id, class_id)),
                        confidence=confidence,
                        bbox=BBox(
                            x=max(float(xyxy[0]), 0.0),
                            y=max(float(xyxy[1]), 0.0),
                            width=max(float(xyxy[2] - xyxy[0]), 1.0),
                            height=max(float(xyxy[3] - xyxy[1]), 1.0),
                        ),
                        track_id=track_id,
                    )
                )

            annotation_frames.append(
                AnnotationFrame(
                    frame_index=frame_source.frame_index,
                    timestamp_ms=frame_source.timestamp_ms,
                    width=width,
                    height=height,
                    image_url=frame_source.image_url,
                    objects=objects,
                )
            )

        return AnnotationsDocument(
            asset_id=asset.id,
            type=asset.type,
            model=request.model_name or Path(model_path).name,
            frames=annotation_frames,
        )

    def _load_ultralytics_model(self, model_path: str) -> Any:
        if model_path in self._models:
            return self._models[model_path]
        try:
            from ultralytics import YOLO
        except Exception as exc:
            raise RuntimeError("ultralytics not installed in this Python environment") from exc

        if self.settings.inference_backend == "tensorrt":
            if Path(model_path).suffix != ".engine":
                raise RuntimeError("TensorRT inference requires a .engine MODEL_PATH")
        self._models[model_path] = YOLO(model_path)
        return self._models[model_path]

    def _resolve_model_path(self, model_name: str | None) -> str:
        candidate = MODEL_ALIASES.get(model_name or "", model_name or self.settings.model_path or "yolo11n.pt")
        path = Path(candidate)
        if path.is_absolute():
            return str(path)

        local_path = Path(self.settings.data_dir).parent / candidate
        if local_path.exists():
            return str(local_path)

        backend_path = Path(__file__).resolve().parents[2] / candidate
        if backend_path.exists():
            return str(backend_path)

        return candidate

    def _result_shape(self, result: Any, asset: Asset, frame_source: FrameSource) -> tuple[int, int]:
        if getattr(result, "orig_shape", None):
            height, width = result.orig_shape[:2]
            return int(height), int(width)
        if frame_source.height and frame_source.width:
            return frame_source.height, frame_source.width
        with Image.open(frame_source.path) as image:
            width, height = image.size
        return height, width

    def _device(self) -> str | None:
        if not self.settings.device:
            return None
        return self.settings.device
