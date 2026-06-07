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


class InferenceService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model: Any | None = None

    @property
    def model_name(self) -> str:
        if self.settings.inference_backend == "ultralytics":
            return Path(self.settings.model_path).name if self.settings.model_path else "ultralytics-default"
        return "mock"

    def predict(self, asset: Asset, request: DetectionRequest) -> AnnotationsDocument:
        if self.settings.inference_backend == "ultralytics":
            return self._predict_ultralytics(asset, request)
        return self._predict_mock(asset)

    def _predict_mock(self, asset: Asset) -> AnnotationsDocument:
        width = asset.width or 640
        height = asset.height or 360
        bbox = BBox(
            x=round(width * 0.35, 2),
            y=round(height * 0.28, 2),
            width=round(width * 0.3, 2),
            height=round(height * 0.42, 2),
        )
        frame = AnnotationFrame(
            frame_index=0,
            timestamp_ms=0,
            width=width,
            height=height,
            objects=[
                DetectionObject(
                    label="railway_target",
                    confidence=0.88,
                    bbox=bbox,
                )
            ],
        )
        return AnnotationsDocument(asset_id=asset.id, type=asset.type, model="mock", frames=[frame])

    def _predict_ultralytics(self, asset: Asset, request: DetectionRequest) -> AnnotationsDocument:
        model = self._load_ultralytics_model()
        source = asset.path
        frames: list[AnnotationFrame] = []
        results = model.predict(
            source=source,
            conf=request.confidence,
            iou=request.iou,
            device=self.settings.device,
            stream=True,
            verbose=False,
        )

        for frame_index, result in enumerate(results):
            if frame_index % request.frame_stride != 0:
                continue
            height, width = self._result_shape(result, asset)
            objects: list[DetectionObject] = []
            names = getattr(result, "names", {}) or {}
            boxes = getattr(result, "boxes", None)
            if boxes is not None:
                for box in boxes:
                    xyxy = box.xyxy[0].tolist()
                    class_id = int(box.cls[0].item()) if box.cls is not None else -1
                    confidence = float(box.conf[0].item()) if box.conf is not None else 0
                    track_id = int(box.id[0].item()) if getattr(box, "id", None) is not None else None
                    objects.append(
                        DetectionObject(
                            label=str(names.get(class_id, class_id)),
                            confidence=confidence,
                            bbox=BBox(
                                x=max(float(xyxy[0]), 0),
                                y=max(float(xyxy[1]), 0),
                                width=max(float(xyxy[2] - xyxy[0]), 1),
                                height=max(float(xyxy[3] - xyxy[1]), 1),
                            ),
                            track_id=track_id,
                        )
                    )
            frames.append(
                AnnotationFrame(
                    frame_index=frame_index,
                    timestamp_ms=self._timestamp_ms(asset, frame_index),
                    width=width,
                    height=height,
                    objects=objects,
                )
            )
        return AnnotationsDocument(asset_id=asset.id, type=asset.type, model=self.model_name, frames=frames)

    def _load_ultralytics_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from ultralytics import YOLO
        except Exception as exc:
            raise RuntimeError("ultralytics is not installed in this Python environment") from exc

        model_path = self.settings.model_path or "yolo11n.pt"
        self._model = YOLO(model_path)
        return self._model

    def _result_shape(self, result: Any, asset: Asset) -> tuple[int, int]:
        if getattr(result, "orig_shape", None):
            height, width = result.orig_shape[:2]
            return int(height), int(width)
        if asset.height and asset.width:
            return asset.height, asset.width
        if asset.type == "image":
            with Image.open(asset.path) as image:
                width, height = image.size
                return height, width
        return 360, 640

    def _timestamp_ms(self, asset: Asset, frame_index: int) -> int:
        if asset.fps:
            return int(frame_index / asset.fps * 1000)
        return 0
