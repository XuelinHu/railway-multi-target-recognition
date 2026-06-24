from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, UniqueConstraint, create_engine, func, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.models.schemas import (
    AnnotationsDocument,
    Asset,
    DetectTask,
    ImageAsset,
    ImageTask,
    ImageTaskResult,
    ImageTaskResultVersion,
    ImageTaskStatus,
    ImageTaskType,
    now_utc,
)


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


class ImageAssetRecord(Base):
    __tablename__ = "image_asset"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    original_name: Mapped[str] = mapped_column(String(255))
    file_name: Mapped[str] = mapped_column(String(255))
    file_url: Mapped[str] = mapped_column(String(500))
    file_path: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    session_id: Mapped[str] = mapped_column(String(100), default="default", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ImageTaskRecord(Base):
    __tablename__ = "image_task"
    __table_args__ = (
        UniqueConstraint("image_id", "task_type", "user_key", "session_id", name="uk_image_task_scope"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    image_id: Mapped[str] = mapped_column(String(64), index=True)
    task_type: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    user_key: Mapped[str] = mapped_column(String(100), default="", index=True)
    session_id: Mapped[str] = mapped_column(String(100), default="default", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ImageTaskResultRecord(Base):
    __tablename__ = "image_task_result"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    image_id: Mapped[str] = mapped_column(String(64), index=True)
    task_type: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(50), default="success", index=True)
    result_image_url: Mapped[str] = mapped_column(String(500), default="")
    result_image_path: Mapped[str] = mapped_column(String(500), default="")
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    annotation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    description_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    has_result: Mapped[bool] = mapped_column(Boolean, default=True)


class ImageTaskResultVersionRecord(Base):
    __tablename__ = "image_task_result_version"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    result_id: Mapped[str] = mapped_column(String(64), index=True)
    task_id: Mapped[str] = mapped_column(String(64), index=True)
    image_id: Mapped[str] = mapped_column(String(64), index=True)
    task_type: Mapped[str] = mapped_column(String(50), index=True)
    version_no: Mapped[int] = mapped_column(Integer, index=True)
    source: Mapped[str] = mapped_column(String(32), default="edited", index=True)
    model_id: Mapped[str] = mapped_column(String(100), default="")
    result_image_url: Mapped[str] = mapped_column(String(500), default="")
    result_image_path: Mapped[str] = mapped_column(String(500), default="")
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    annotation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    description_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PostgresStore:
    def __init__(self, database_url: str) -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    def create_asset(self, asset: Asset) -> Asset:
        with self.session_factory.begin() as session:
            record = AssetRecord(
                id=asset.id,
                created_at=asset.created_at,
                payload=asset.model_dump(mode="json"),
            )
            session.merge(record)
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

    def create_image_asset(self, image: ImageAsset) -> ImageAsset:
        with self.session_factory.begin() as session:
            session.add(self._image_asset_record(image))
        return image

    def get_image_asset(self, image_id: str) -> ImageAsset | None:
        with self.session_factory() as session:
            record = session.get(ImageAssetRecord, image_id)
            return self._image_asset_from_record(record) if record else None

    def list_image_assets(
        self,
        task_type: ImageTaskType | None = None,
        session_id: str = "default",
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[ImageAsset], int]:
        offset = max(page - 1, 0) * page_size
        with self.session_factory() as session:
            base = (
                select(ImageAssetRecord)
                .where(ImageAssetRecord.session_id == session_id)
                .order_by(ImageAssetRecord.created_at.desc())
            )
            records = session.scalars(base.offset(offset).limit(page_size)).all()
            total = session.scalar(select(func.count()).select_from(ImageAssetRecord).where(ImageAssetRecord.session_id == session_id))
            images = [self._image_asset_from_record(record) for record in records]
            if task_type:
                for image in images:
                    task = self.get_image_task(image.image_id, task_type, session_id)
                    result = self.get_image_task_result(image.image_id, task_type, session_id)
                    image.task_status = task.status if task else "idle"
                    image.has_current_task_result = result is not None
            return images, int(total or 0)

    def create_or_get_image_task(
        self,
        image_id: str,
        task_type: ImageTaskType,
        session_id: str = "default",
        user_id: str | None = None,
    ) -> ImageTask:
        user_key = user_id or ""
        with self.session_factory.begin() as session:
            existing = session.scalar(
                select(ImageTaskRecord).where(
                    ImageTaskRecord.image_id == image_id,
                    ImageTaskRecord.task_type == task_type,
                    ImageTaskRecord.session_id == session_id,
                    ImageTaskRecord.user_key == user_key,
                )
            )
            if existing:
                return self._image_task_from_record(existing)
            task = ImageTask(image_id=image_id, task_type=task_type, session_id=session_id, user_id=user_id)
            session.add(self._image_task_record(task))
            return task

    def update_image_task_status(self, task_id: str, status: ImageTaskStatus) -> None:
        with self.session_factory.begin() as session:
            record = session.get(ImageTaskRecord, task_id)
            if record:
                record.status = status
                record.updated_at = now_utc()

    def get_image_task(
        self,
        image_id: str,
        task_type: ImageTaskType,
        session_id: str = "default",
    ) -> ImageTask | None:
        with self.session_factory() as session:
            record = session.scalar(
                select(ImageTaskRecord).where(
                    ImageTaskRecord.image_id == image_id,
                    ImageTaskRecord.task_type == task_type,
                    ImageTaskRecord.session_id == session_id,
                )
            )
            return self._image_task_from_record(record) if record else None

    def save_image_task_result(self, result: ImageTaskResult) -> tuple[ImageTaskResult, ImageTaskResultVersion]:
        with self.session_factory.begin() as session:
            record = session.scalar(select(ImageTaskResultRecord).where(ImageTaskResultRecord.task_id == result.task_id))
            if record is None:
                record = self._image_task_result_record(result)
                session.add(record)
            else:
                record.status = result.status
                record.result_image_url = result.result_image_url
                record.result_image_path = result.result_image_path
                record.result_json = result.result_json
                record.annotation_json = result.annotation_json
                record.description_text = result.description_text
                record.updated_at = now_utc()
                result.result_id = record.id
            task = session.get(ImageTaskRecord, result.task_id)
            if task:
                task.status = result.status
                task.updated_at = now_utc()
            version_no = self._next_result_version_no(session, result.task_id)
            version = ImageTaskResultVersion(
                result_id=record.id,
                task_id=result.task_id,
                image_id=result.image_id,
                task_type=result.task_type,
                version_no=version_no,
                source=result.source,
                model_id=result.model_id,
                result_image_url=result.result_image_url,
                result_image_path=result.result_image_path,
                result_json=result.result_json,
                annotation_json=result.annotation_json,
                description_text=result.description_text,
            )
            session.add(self._image_task_result_version_record(version))
            result.latest_version_id = version.version_id
            result.latest_version_no = version.version_no
        return result, version

    def get_image_task_result(
        self,
        image_id: str,
        task_type: ImageTaskType,
        session_id: str = "default",
    ) -> ImageTaskResult | None:
        with self.session_factory() as session:
            task = session.scalar(
                select(ImageTaskRecord).where(
                    ImageTaskRecord.image_id == image_id,
                    ImageTaskRecord.task_type == task_type,
                    ImageTaskRecord.session_id == session_id,
                )
            )
            if not task:
                return None
            record = session.scalar(select(ImageTaskResultRecord).where(ImageTaskResultRecord.task_id == task.id))
            return self._image_task_result_from_record(record) if record else None

    def update_image_task_annotation(
        self,
        task_id: str,
        image_id: str,
        task_type: ImageTaskType,
        annotation_json: dict,
    ) -> ImageTaskResult | None:
        with self.session_factory.begin() as session:
            record = session.scalar(select(ImageTaskResultRecord).where(ImageTaskResultRecord.task_id == task_id))
            if record is None:
                return None
            record.image_id = image_id
            record.task_type = task_type
            record.annotation_json = annotation_json
            record.updated_at = now_utc()
            return self._image_task_result_from_record(record)

    def list_image_task_result_versions(
        self,
        image_id: str,
        task_type: ImageTaskType,
        session_id: str = "default",
    ) -> list[ImageTaskResultVersion]:
        with self.session_factory() as session:
            task = session.scalar(
                select(ImageTaskRecord).where(
                    ImageTaskRecord.image_id == image_id,
                    ImageTaskRecord.task_type == task_type,
                    ImageTaskRecord.session_id == session_id,
                )
            )
            if task is None:
                return []
            records = session.scalars(
                select(ImageTaskResultVersionRecord)
                .where(ImageTaskResultVersionRecord.task_id == task.id)
                .order_by(ImageTaskResultVersionRecord.version_no.desc())
            ).all()
            return [self._image_task_result_version_from_record(record) for record in records]

    def get_image_task_result_version(self, version_id: str) -> ImageTaskResultVersion | None:
        with self.session_factory() as session:
            record = session.get(ImageTaskResultVersionRecord, version_id)
            return self._image_task_result_version_from_record(record) if record else None

    def restore_image_task_result_version(self, version_id: str) -> tuple[ImageTaskResult, ImageTaskResultVersion] | None:
        version = self.get_image_task_result_version(version_id)
        if version is None:
            return None
        result = ImageTaskResult(
            task_id=version.task_id,
            image_id=version.image_id,
            task_type=version.task_type,
            result_image_url=version.result_image_url,
            result_image_path=version.result_image_path,
            result_json=version.result_json,
            annotation_json=version.annotation_json,
            description_text=version.description_text,
            source="edited",
            model_id=version.model_id,
        )
        return self.save_image_task_result(result)

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

    def _image_asset_record(self, image: ImageAsset) -> ImageAssetRecord:
        return ImageAssetRecord(
            id=image.image_id,
            original_name=image.original_name,
            file_name=image.file_name,
            file_url=image.file_url,
            file_path=image.file_path,
            mime_type=image.mime_type,
            file_size=image.file_size,
            width=image.width,
            height=image.height,
            user_id=image.user_id,
            session_id=image.session_id,
            created_at=image.created_at,
            updated_at=image.updated_at,
        )

    def _image_asset_from_record(self, record: ImageAssetRecord) -> ImageAsset:
        return ImageAsset(
            image_id=record.id,
            original_name=record.original_name,
            file_name=record.file_name,
            file_url=record.file_url,
            file_path=record.file_path,
            mime_type=record.mime_type,
            file_size=record.file_size,
            width=record.width,
            height=record.height,
            user_id=record.user_id,
            session_id=record.session_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _image_task_record(self, task: ImageTask) -> ImageTaskRecord:
        return ImageTaskRecord(
            id=task.task_id,
            image_id=task.image_id,
            task_type=task.task_type,
            status=task.status,
            user_id=task.user_id,
            user_key=task.user_id or "",
            session_id=task.session_id,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    def _image_task_from_record(self, record: ImageTaskRecord) -> ImageTask:
        return ImageTask(
            task_id=record.id,
            image_id=record.image_id,
            task_type=record.task_type,
            status=record.status,
            user_id=record.user_id,
            session_id=record.session_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _image_task_result_record(self, result: ImageTaskResult) -> ImageTaskResultRecord:
        return ImageTaskResultRecord(
            id=result.result_id,
            task_id=result.task_id,
            image_id=result.image_id,
            task_type=result.task_type,
            status=result.status,
            result_image_url=result.result_image_url,
            result_image_path=result.result_image_path,
            result_json=result.result_json,
            annotation_json=result.annotation_json,
            description_text=result.description_text,
            created_at=result.created_at,
            updated_at=result.updated_at,
        )

    def _image_task_result_from_record(self, record: ImageTaskResultRecord) -> ImageTaskResult:
        latest = self._latest_version_for_task(record.task_id)
        return ImageTaskResult(
            result_id=record.id,
            task_id=record.task_id,
            image_id=record.image_id,
            task_type=record.task_type,
            status=record.status,
            result_image_url=record.result_image_url,
            result_image_path=record.result_image_path,
            result_json=record.result_json,
            annotation_json=record.annotation_json,
            description_text=record.description_text,
            created_at=record.created_at,
            updated_at=record.updated_at,
            latest_version_id=latest.version_id if latest else None,
            latest_version_no=latest.version_no if latest else None,
        )

    def _image_task_result_version_record(self, version: ImageTaskResultVersion) -> ImageTaskResultVersionRecord:
        return ImageTaskResultVersionRecord(
            id=version.version_id,
            result_id=version.result_id,
            task_id=version.task_id,
            image_id=version.image_id,
            task_type=version.task_type,
            version_no=version.version_no,
            source=version.source,
            model_id=version.model_id,
            result_image_url=version.result_image_url,
            result_image_path=version.result_image_path,
            result_json=version.result_json,
            annotation_json=version.annotation_json,
            description_text=version.description_text,
            created_at=version.created_at,
        )

    def _image_task_result_version_from_record(self, record: ImageTaskResultVersionRecord) -> ImageTaskResultVersion:
        return ImageTaskResultVersion(
            version_id=record.id,
            result_id=record.result_id,
            task_id=record.task_id,
            image_id=record.image_id,
            task_type=record.task_type,
            version_no=record.version_no,
            source=record.source,
            model_id=record.model_id,
            result_image_url=record.result_image_url,
            result_image_path=record.result_image_path,
            result_json=record.result_json,
            annotation_json=record.annotation_json,
            description_text=record.description_text,
            created_at=record.created_at,
        )

    def _next_result_version_no(self, session: Session, task_id: str) -> int:
        latest = session.scalar(
            select(func.max(ImageTaskResultVersionRecord.version_no)).where(ImageTaskResultVersionRecord.task_id == task_id)
        )
        return int(latest or 0) + 1

    def _latest_version_for_task(self, task_id: str) -> ImageTaskResultVersion | None:
        with self.session_factory() as session:
            record = session.scalar(
                select(ImageTaskResultVersionRecord)
                .where(ImageTaskResultVersionRecord.task_id == task_id)
                .order_by(ImageTaskResultVersionRecord.version_no.desc())
                .limit(1)
            )
            return self._image_task_result_version_from_record(record) if record else None
