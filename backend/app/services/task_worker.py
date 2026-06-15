import logging
from threading import Event, Thread

from app.repositories.postgres_store import PostgresStore
from app.services.task_service import TaskService


logger = logging.getLogger(__name__)


class DatabaseTaskWorker:
    def __init__(
        self,
        store: PostgresStore,
        task_service: TaskService,
        poll_interval_seconds: float,
    ) -> None:
        self.store = store
        self.task_service = task_service
        self.poll_interval_seconds = poll_interval_seconds
        self._stop_event = Event()
        self._thread = Thread(target=self._run, name="postgres-task-worker", daemon=True)

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=max(self.poll_interval_seconds * 2, 2))

    def _run(self) -> None:
        logger.info("PostgreSQL task worker started")
        while not self._stop_event.is_set():
            try:
                task = self.store.claim_next_task()
                if task is None:
                    self._stop_event.wait(self.poll_interval_seconds)
                    continue
                self.task_service.run_detection(task.id, claimed_task=task)
            except Exception:
                logger.exception("PostgreSQL task worker iteration failed")
                self._stop_event.wait(self.poll_interval_seconds)
        logger.info("PostgreSQL task worker stopped")
