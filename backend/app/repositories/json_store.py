import json
from pathlib import Path
from threading import Lock
from typing import Any

from app.models.schemas import AnnotationsDocument, Asset, DetectTask


class JsonStore:
    """Small local persistence layer used until PostgreSQL is introduced."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.db_path.exists():
            self._write({"assets": {}, "tasks": {}, "annotations": {}})

    def _read(self) -> dict[str, Any]:
        with self.db_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write(self, data: dict[str, Any]) -> None:
        tmp_path = self.db_path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        tmp_path.replace(self.db_path)

    def create_asset(self, asset: Asset) -> Asset:
        with self._lock:
            data = self._read()
            data["assets"][asset.id] = asset.model_dump(mode="json")
            self._write(data)
        return asset

    def list_assets(self) -> list[Asset]:
        data = self._read()
        assets = [Asset.model_validate(item) for item in data["assets"].values()]
        return sorted(assets, key=lambda item: item.created_at, reverse=True)

    def get_asset(self, asset_id: str) -> Asset | None:
        data = self._read()
        raw = data["assets"].get(asset_id)
        return Asset.model_validate(raw) if raw else None

    def create_task(self, task: DetectTask) -> DetectTask:
        with self._lock:
            data = self._read()
            data["tasks"][task.id] = task.model_dump(mode="json")
            self._write(data)
        return task

    def update_task(self, task: DetectTask) -> DetectTask:
        with self._lock:
            data = self._read()
            data["tasks"][task.id] = task.model_dump(mode="json")
            self._write(data)
        return task

    def list_tasks(self) -> list[DetectTask]:
        data = self._read()
        tasks = [DetectTask.model_validate(item) for item in data["tasks"].values()]
        return sorted(tasks, key=lambda item: item.created_at, reverse=True)

    def get_task(self, task_id: str) -> DetectTask | None:
        data = self._read()
        raw = data["tasks"].get(task_id)
        return DetectTask.model_validate(raw) if raw else None

    def save_annotations(self, annotations: AnnotationsDocument) -> AnnotationsDocument:
        with self._lock:
            data = self._read()
            data["annotations"][annotations.asset_id] = annotations.model_dump(mode="json")
            self._write(data)
        return annotations

    def get_annotations(self, asset_id: str) -> AnnotationsDocument | None:
        data = self._read()
        raw = data["annotations"].get(asset_id)
        return AnnotationsDocument.model_validate(raw) if raw else None
