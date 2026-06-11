import shutil
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile
from PIL import Image

from app.models.schemas import Asset


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


@dataclass(frozen=True)
class FrameSource:
    frame_index: int
    timestamp_ms: int
    path: Path
    width: int
    height: int
    image_url: str


class StorageService:
    def __init__(self, upload_dir: Path) -> None:
        self.upload_dir = upload_dir
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def save_upload(self, upload: UploadFile) -> Asset:
        filename = Path(upload.filename or "upload.bin").name
        extension = Path(filename).suffix.lower()
        asset_type = self._guess_asset_type(upload.content_type or "", extension)

        asset = Asset(
            filename=filename,
            content_type=upload.content_type or "application/octet-stream",
            type=asset_type,
            path="",
            size_bytes=0,
        )
        asset_dir = self.upload_dir / asset.id
        asset_dir.mkdir(parents=True, exist_ok=True)
        target_path = asset_dir / filename

        with target_path.open("wb") as handle:
            shutil.copyfileobj(upload.file, handle)

        asset.path = str(target_path)
        asset.size_bytes = target_path.stat().st_size
        if asset.type == "image":
            self._populate_image_metadata(asset, target_path)
        elif asset.type == "video":
            self._populate_video_metadata(asset, target_path)
        return asset

    def extract_frames(
        self,
        asset: Asset,
        frame_stride: int = 1,
        max_frames: int | None = None,
    ) -> list[FrameSource]:
        if asset.type == "image":
            return [self._extract_image_frame(asset)]
        if asset.type == "video":
            return self._extract_video_frames(asset, frame_stride=frame_stride, max_frames=max_frames)
        raise ValueError(f"unsupported asset type: {asset.type}")

    def frame_path(self, asset_id: str, frame_index: int) -> Path:
        return self.upload_dir / asset_id / "frames" / f"frame_{frame_index:06d}.jpg"

    def _guess_asset_type(self, content_type: str, extension: str) -> str:
        if content_type.startswith("image/") or extension in IMAGE_EXTENSIONS:
            return "image"
        if content_type.startswith("video/") or extension in VIDEO_EXTENSIONS:
            return "video"
        return "unknown"

    def _populate_image_metadata(self, asset: Asset, path: Path) -> None:
        with Image.open(path) as image:
            asset.width, asset.height = image.size

    def _populate_video_metadata(self, asset: Asset, path: Path) -> None:
        try:
            import cv2
        except Exception:
            return

        capture = cv2.VideoCapture(str(path))
        try:
            if not capture.isOpened():
                return
            fps = capture.get(cv2.CAP_PROP_FPS) or 0
            frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            asset.width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0) or None
            asset.height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0) or None
            asset.frame_count = int(frame_count) if frame_count else None
            asset.fps = float(fps) if fps else None
            asset.duration_ms = int(frame_count / fps * 1000) if fps and frame_count else None
        finally:
            capture.release()

    def _frame_dir(self, asset: Asset) -> Path:
        frame_dir = Path(asset.path).parent / "frames"
        frame_dir.mkdir(parents=True, exist_ok=True)
        return frame_dir

    def _extract_image_frame(self, asset: Asset) -> FrameSource:
        source_path = Path(asset.path)
        frame_path = self._frame_dir(asset) / "frame_000000.jpg"
        with Image.open(source_path) as image:
            rgb_image = image.convert("RGB")
            rgb_image.save(frame_path, format="JPEG", quality=92)
            width, height = rgb_image.size
        return FrameSource(
            frame_index=0,
            timestamp_ms=0,
            path=frame_path,
            width=width,
            height=height,
            image_url=f"/api/assets/{asset.id}/frames/0/image",
        )

    def _extract_video_frames(
        self,
        asset: Asset,
        frame_stride: int,
        max_frames: int | None,
    ) -> list[FrameSource]:
        try:
            import cv2
        except Exception as exc:
            raise RuntimeError("opencv-python-headless is required for video frame extraction") from exc

        capture = cv2.VideoCapture(asset.path)
        if not capture.isOpened():
            raise RuntimeError(f"could not open video: {asset.filename}")

        frames: list[FrameSource] = []
        frame_dir = self._frame_dir(asset)
        fps = capture.get(cv2.CAP_PROP_FPS) or asset.fps or 0
        raw_index = 0
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                if raw_index % frame_stride != 0:
                    raw_index += 1
                    continue
                frame_path = frame_dir / f"frame_{raw_index:06d}.jpg"
                cv2.imwrite(str(frame_path), frame)
                height, width = frame.shape[:2]
                timestamp_ms = int(raw_index / fps * 1000) if fps else 0
                frames.append(
                    FrameSource(
                        frame_index=raw_index,
                        timestamp_ms=timestamp_ms,
                        path=frame_path,
                        width=int(width),
                        height=int(height),
                        image_url=f"/api/assets/{asset.id}/frames/{raw_index}/image",
                    )
                )
                if max_frames is not None and len(frames) >= max_frames:
                    break
                raw_index += 1
        finally:
            capture.release()

        if not frames:
            raise RuntimeError(f"no frames extracted from video: {asset.filename}")
        return frames
