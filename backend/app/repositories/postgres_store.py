from datetime import datetime

from sqlalchemy import JSON, DateTime, String, create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.models.schemas import AnnotationsDocument, Asset, DetectTask, now_utc


class Base(DeclarativeBase):
    pass


class AssetRecord(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class TaskRecord(Base):
    __tablename__ = "detect_tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class AnnotationRecord(Base):
    __tablename__ = "annotations"

    asset_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class PostgresStore:
    def __init__(self, database_url: str) -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    def create_asset(self, asset: Asset) -> Asset:
        with self.session_factory.begin() as session:
            session.add(
                AssetRecord(
                    id=asset.id,
                    created_at=asset.created_at,
                    payload=asset.model_dump(mode="json"),
                )
            )
        return asset

    def list_assets(self) -> list[Asset]:
        with self.session_factory() as session:
            records = session.scalars(select(AssetRecord).order_by(AssetRecord.created_at.desc())).all()
            return [Asset.model_validate(record.payload) for record in records]

    def get_asset(self, asset_id: str) -> Asset | None:
        with self.session_factory() as session:
            record = session.get(AssetRecord, asset_id)
            return Asset.model_validate(record.payload) if record else None

    def create_task(self, task: DetectTask) -> DetectTask:
        with self.session_factory.begin() as session:
            session.add(self._task_record(task))
        return task

    def update_task(self, task: DetectTask) -> DetectTask:
        with self.session_factory.begin() as session:
            record = session.get(TaskRecord, task.id)
            if record is None:
                session.add(self._task_record(task))
            else:
                record.asset_id = task.asset_id
                record.status = task.status
                record.payload = task.model_dump(mode="json")
        return task

    def claim_next_task(self) -> DetectTask | None:
        with self.session_factory.begin() as session:
            statement = (
                select(TaskRecord)
                .where(TaskRecord.status == "queued")
                .order_by(TaskRecord.created_at.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            record = session.scalar(statement)
            if record is None:
                return None
            task = DetectTask.model_validate(record.payload)
            task.status = "running"
            task.progress = 0.05
            task.started_at = now_utc()
            record.status = task.status
            record.payload = task.model_dump(mode="json")
            return task

    def list_tasks(self) -> list[DetectTask]:
        with self.session_factory() as session:
            records = session.scalars(select(TaskRecord).order_by(TaskRecord.created_at.desc())).all()
            return [DetectTask.model_validate(record.payload) for record in records]

    def get_task(self, task_id: str) -> DetectTask | None:
        with self.session_factory() as session:
            record = session.get(TaskRecord, task_id)
            return DetectTask.model_validate(record.payload) if record else None

    def save_annotations(self, annotations: AnnotationsDocument) -> AnnotationsDocument:
        with self.session_factory.begin() as session:
            record = session.get(AnnotationRecord, annotations.asset_id)
            payload = annotations.model_dump(mode="json")
            if record is None:
                session.add(
                    AnnotationRecord(
                        asset_id=annotations.asset_id,
                        updated_at=annotations.updated_at,
                        payload=payload,
                    )
                )
            else:
                record.updated_at = annotations.updated_at
                record.payload = payload
        return annotations

    def get_annotations(self, asset_id: str) -> AnnotationsDocument | None:
        with self.session_factory() as session:
            record = session.get(AnnotationRecord, asset_id)
            return AnnotationsDocument.model_validate(record.payload) if record else None

    def close(self) -> None:
        self.engine.dispose()

    def healthcheck(self) -> bool:
        with self.engine.connect() as connection:
            return connection.execute(text("SELECT 1")).scalar_one() == 1

    def _task_record(self, task: DetectTask) -> TaskRecord:
        return TaskRecord(
            id=task.id,
            asset_id=task.asset_id,
            status=task.status,
            created_at=task.created_at,
            payload=task.model_dump(mode="json"),
        )
