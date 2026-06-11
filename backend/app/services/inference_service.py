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


class InferenceService:
    def __init__(self, settings: Settings, storage: StorageService) -> None:
        self.settings = settings
        self.storage = storage
        self._model: Any | None = None

    @property
    def model_name(self) -> str:
        if self.settings.inference_backend == "ultralytics":
            return Path(self.settings.model_path).name if self.settings.model_path else "ultralytics-default"
        return "mock"

    def predict(self, asset: Asset, request: DetectionRequest) -> AnnotationsDocument:
        frames = self.storage.extract_frames(
            asset,
            frame_stride=request.frame_stride,
            max_frames=request.max_frames,
        )
        if self.settings.inference_backend == "ultralytics":
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
        model = self._load_ultralytics_model()
        annotation_frames: list[AnnotationFrame] = []

        for frame_source in frames:
            result = model.predict(
                source=str(frame_source.path),
                conf=request.confidence,
                iou=request.iou,
                device=self.settings.device,
                verbose=False,
            )[0]
            height, width = self._result_shape(result, asset, frame_source)
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
        return AnnotationsDocument(asset_id=asset.id, type=asset.type, model=self.model_name, frames=annotation_frames)

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

    def _result_shape(self, result: Any, asset: Asset, frame_source: FrameSource) -> tuple[int, int]:
        if getattr(result, "orig_shape", None):
            height, width = result.orig_shape[:2]
            return int(height), int(width)
        if frame_source.height and frame_source.width:
            return frame_source.height, frame_source.width
        with Image.open(frame_source.path) as image:
            width, height = image.size
            return height, width
