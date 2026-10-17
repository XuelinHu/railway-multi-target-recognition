from __future__ import annotations

import json
import threading
from pathlib import Path

from app.models.schemas import TrainingMetric, TrainingTask, now_utc


class TrainingService:
    def __init__(self, store, data_dir: Path) -> None:
        self.store = store
        self.data_dir = data_dir
        self._threads: dict[str, threading.Thread] = {}

    def start(self, task: TrainingTask) -> None:
        thread = threading.Thread(target=self._run, args=(task,), daemon=True, name=f"training-{task.training_id}")
        self._threads[task.training_id] = thread
        thread.start()

    def _run(self, task: TrainingTask) -> None:
        try:
            started = now_utc()
            self.store.update_training_task(task.training_id, status="running", started_at=started)
            dataset_dir = self.data_dir / "training" / task.training_id / "dataset"
            output_dir = self.data_dir / "training" / task.training_id / "runs"
            self._build_dataset(task, dataset_dir)
            self.store.update_training_task(task.training_id, dataset_dir=str(dataset_dir), output_dir=str(output_dir))
            from ultralytics import YOLO

            model = YOLO(task.model_name)

            def on_epoch_end(trainer) -> None:
                metrics = getattr(trainer, "metrics", {}) or {}
                values = getattr(trainer, "label_loss_items", lambda *args, **kwargs: {})
                losses = values(getattr(trainer, "tloss", None), prefix="train") or {}
                self.store.save_training_metric(TrainingMetric(
                    training_id=task.training_id, epoch=int(getattr(trainer, "epoch", 0)) + 1,
                    total_epochs=task.epochs,
                    train_loss=_float_loss(losses),
                    precision=_metric(metrics, "metrics/precision(B)", "metrics/precision(P)"),
                    recall=_metric(metrics, "metrics/recall(B)", "metrics/recall(P)"),
                    map50=_metric(metrics, "metrics/mAP50(B)", "metrics/mAP50(P)"),
                    map50_95=_metric(metrics, "metrics/mAP50-95(B)", "metrics/mAP50-95(P)"),
                    learning_rate=_metric(getattr(trainer, "lr", {}) or {}, "lr/pg0"),
                ))

            model.add_callback("on_fit_epoch_end", on_epoch_end)
            model.train(data=str(dataset_dir / "data.yaml"), epochs=task.epochs, batch=task.batch_size, imgsz=task.image_size, project=str(output_dir), name="run", exist_ok=True)
            best = output_dir / "run" / "weights" / "best.pt"
            self.store.update_training_task(task.training_id, status="completed", best_model_path=str(best) if best.exists() else "", finished_at=now_utc())
        except Exception as exc:
            self.store.update_training_task(task.training_id, status="failed", error=f"{type(exc).__name__}: {exc}", finished_at=now_utc())

    def _build_dataset(self, task: TrainingTask, root: Path) -> None:
        names = self._label_names(task)
        for split, image_ids in (("train", task.train_image_ids), ("val", task.val_image_ids)):
            (root / "images" / split).mkdir(parents=True, exist_ok=True)
            (root / "labels" / split).mkdir(parents=True, exist_ok=True)
            for image_id in image_ids:
                image = self.store.get_image_asset(image_id)
                if image is None or not Path(image.file_path).is_file():
                    continue
                target_name = f"{image_id}{Path(image.file_path).suffix.lower() or '.jpg'}"
                target = root / "images" / split / target_name
                target.write_bytes(Path(image.file_path).read_bytes())
                result = self.store.get_image_task_result(image_id, task.task_type, image.session_id, image.user_id)
                (root / "labels" / split / f"{image_id}.txt").write_text(self._labels(task, result, image.width or 1, image.height or 1, names), encoding="utf-8")
        yaml = {"path": str(root), "train": "images/train", "val": "images/val", "names": names}
        (root / "data.yaml").write_text(json.dumps(yaml, ensure_ascii=False, indent=2), encoding="utf-8")

    def _label_names(self, task: TrainingTask) -> dict[int, str]:
        labels = self.store.list_label_configs()
        return {index: label.english_name for index, label in enumerate(labels)} or {0: "railway_target"}

    def _labels(self, task: TrainingTask, result, width: int, height: int, names: dict[int, str]) -> str:
        if result is None or not result.result_json:
            return ""
        data = result.result_json
        lines: list[str] = []
        if task.task_type == "detection":
            items = data.get("boxes", [])
            for item in items:
                index = _class_index(item.get("label"), names)
                x, y, w, h = float(item.get("x", 0)), float(item.get("y", 0)), float(item.get("width", 0)), float(item.get("height", 0))
                lines.append(f"{index} {(x + w / 2) / width:.6f} {(y + h / 2) / height:.6f} {w / width:.6f} {h / height:.6f}")
        elif task.task_type == "segmentation":
            for item in data.get("segments", []):
                polygon = item.get("polygon", [])
                if len(polygon) >= 6:
                    index = _class_index(item.get("label"), names)
                    points = " ".join(f"{float(point[0]) / width:.6f} {float(point[1]) / height:.6f}" for point in polygon)
                    lines.append(f"{index} {points}")
        elif task.task_type == "pose":
            for point in data.get("keypoints", []):
                lines.append(f"{_class_index(point.get('name'), names)} 0.5 0.5 1 1")
        return "\n".join(lines)


def _class_index(label, names: dict[int, str]) -> int:
    label = str(label or "railway_target")
    for index, name in names.items():
        if name == label or name in label or label in name:
            return index
    return 0


def _metric(values: dict, *keys: str) -> float | None:
    for key in keys:
        if key in values:
            try:
                return float(values[key])
            except (TypeError, ValueError):
                return None
    return None


def _float_loss(values: dict) -> float | None:
    if not values:
        return None
    numbers = [float(value) for value in values.values() if isinstance(value, (int, float))]
    return sum(numbers) / len(numbers) if numbers else None
