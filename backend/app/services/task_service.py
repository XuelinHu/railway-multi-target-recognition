from app.models.schemas import DetectTask, DetectionRequest, now_utc
from app.repositories.postgres_store import PostgresStore
from app.services.inference_service import InferenceService


class TaskService:
    def __init__(self, store: PostgresStore, inference: InferenceService) -> None:
        self.store = store
        self.inference = inference

    def create_detection_task(self, request: DetectionRequest) -> DetectTask:
        task = DetectTask(
            asset_id=request.asset_id,
            params=request,
            model_name=self.inference.model_name,
        )
        return self.store.create_task(task)

    def run_detection(self, task_id: str, claimed_task: DetectTask | None = None) -> None:
        task = claimed_task or self.store.get_task(task_id)
        if task is None:
            return

        asset = self.store.get_asset(task.asset_id)
        if asset is None:
            task.status = "failed"
            task.error = f"asset not found: {task.asset_id}"
            task.finished_at = now_utc()
            self.store.update_task(task)
            return

        try:
            if claimed_task is None:
                task.status = "running"
                task.progress = 0.1
                task.started_at = now_utc()
                self.store.update_task(task)

            annotations = self.inference.predict(asset, task.params)
            self.store.save_annotations(annotations)

            task.status = "completed"
            task.progress = 1
            task.finished_at = now_utc()
            self.store.update_task(task)
        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)
            task.finished_at = now_utc()
            self.store.update_task(task)
