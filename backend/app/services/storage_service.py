import shutil
from pathlib import Path

from fastapi import UploadFile
from PIL import Image

from app.models.schemas import Asset


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


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
            asset.fps = float(fps) if fps else None
            asset.duration_ms = int(frame_count / fps * 1000) if fps and frame_count else None
        finally:
            capture.release()
