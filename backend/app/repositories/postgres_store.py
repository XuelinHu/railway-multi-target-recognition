from datetime import datetime
import re

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint, create_engine, func, or_, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.models.schemas import (
    AnnotationsDocument,
    AuthUser,
    Asset,
    DetectTask,
    ImageAsset,
    ImageTask,
    ImageTaskResult,
    ImageTaskResultVersion,
    ImageTaskStatus,
    ImageTaskType,
    LabelConfig,
    VideoCaptionBatch,
    VideoCaptionFrame,
    VideoCaptionVideo,
    TrainingMetric,
    TrainingTask,
    now_utc,
)


class Base(DeclarativeBase):
    pass


def _task_result_count(task_type: ImageTaskType, result: ImageTaskResult | None) -> int:
    if result is None or not result.result_json:
        return 0
    payload = result.result_json
    if task_type == "detection":
        return len(payload.get("boxes", []))
    if task_type == "segmentation":
        return len(payload.get("segments", []))
    if task_type == "pose":
        names = [str(point.get("name", "")) for point in payload.get("keypoints", []) if isinstance(point, dict)]
        people = {match.group(1) for name in names if (match := re.match(r"person_(\d+)_", name))}
        return len(people) or (len(names) // 17 if names else 0)
    if task_type == "caption":
        return len(str(result.description_text or payload.get("description", "")).strip())
    return 0


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


class UserRecord(Base):
    __tablename__ = "app_user"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="student", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AuthSessionRecord(Base):
    __tablename__ = "auth_session"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


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
    review_status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    submitted_by: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_comment: Mapped[str] = mapped_column(Text, default="")


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


class LabelConfigRecord(Base):
    __tablename__ = "label_config"

    label_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    english_name: Mapped[str] = mapped_column(String(120), index=True)
    chinese_name: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    thumbnail_url: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class VideoCaptionBatchRecord(Base):
    __tablename__ = "video_caption_batch"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    source_dir: Mapped[str] = mapped_column(String(1000), default="")
    output_dir: Mapped[str] = mapped_column(String(1000), default="")
    model_id: Mapped[str] = mapped_column(String(160), default="")
    prompt: Mapped[str] = mapped_column(Text, default="")
    frame_interval_seconds: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    total_videos: Mapped[int] = mapped_column(Integer, default=0)
    total_frames: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class VideoCaptionVideoRecord(Base):
    __tablename__ = "video_caption_video"
    __table_args__ = (
        UniqueConstraint("batch_id", "source_path", name="uk_video_caption_video_source"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str] = mapped_column(String(255), index=True)
    display_name: Mapped[str] = mapped_column(String(500), default="")
    keywords_json: Mapped[list] = mapped_column(JSON, default=list)
    source_path: Mapped[str] = mapped_column(String(1000))
    frame_dir: Mapped[str] = mapped_column(String(1000), default="")
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frame_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    similar_frames_skipped: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class VideoCaptionFrameRecord(Base):
    __tablename__ = "video_caption_frame"
    __table_args__ = (
        UniqueConstraint("video_id", "frame_index", name="uk_video_caption_frame_index"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(64), index=True)
    video_id: Mapped[str] = mapped_column(String(64), index=True)
    frame_index: Mapped[int] = mapped_column(Integer, index=True)
    timestamp_ms: Mapped[int] = mapped_column(Integer, index=True)
    image_path: Mapped[str] = mapped_column(String(1000))
    image_url: Mapped[str] = mapped_column(String(500), default="")
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description_text: Mapped[str] = mapped_column(Text, default="")
    description_en: Mapped[str] = mapped_column(Text, default="")
    description_manual: Mapped[str] = mapped_column(Text, default="")
    safety_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_id: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class TrainingTaskRecord(Base):
    __tablename__ = "training_task"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    task_type: Mapped[str] = mapped_column(String(32), index=True)
    model_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), index=True)
    train_image_ids: Mapped[list] = mapped_column(JSON, default=list)
    val_image_ids: Mapped[list] = mapped_column(JSON, default=list)
    epochs: Mapped[int] = mapped_column(Integer)
    batch_size: Mapped[int] = mapped_column(Integer)
    image_size: Mapped[int] = mapped_column(Integer)
    dataset_dir: Mapped[str] = mapped_column(String(1000), default="")
    output_dir: Mapped[str] = mapped_column(String(1000), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    best_model_path: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TrainingMetricRecord(Base):
    __tablename__ = "training_metric"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    training_id: Mapped[str] = mapped_column(String(64), index=True)
    epoch: Mapped[int] = mapped_column(Integer)
    total_epochs: Mapped[int] = mapped_column(Integer)
    train_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    val_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    map50: Mapped[float | None] = mapped_column(Float, nullable=True)
    map50_95: Mapped[float | None] = mapped_column(Float, nullable=True)
    learning_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PostgresStore:
    def __init__(self, database_url: str) -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        self._ensure_label_config_schema(database_url)
        self._ensure_image_task_review_schema(database_url)
        self._ensure_admin_user()
        self._seed_railway_labels(database_url)
        from app.core.config import get_settings

        video_database_url = get_settings().video_database_url
        if not video_database_url and database_url.startswith("postgresql"):
            video_database_url = make_url(database_url).set(database="railway_video_captions").render_as_string(hide_password=False)
        video_database_url = video_database_url or database_url
        if video_database_url == database_url:
            self.video_engine = self.engine
            self.video_session_factory = self.session_factory
        else:
            self.video_engine = create_engine(video_database_url, pool_pre_ping=True)
            self.video_session_factory = sessionmaker(self.video_engine, expire_on_commit=False)
            Base.metadata.create_all(
                self.video_engine,
                tables=[VideoCaptionBatchRecord.__table__, VideoCaptionVideoRecord.__table__, VideoCaptionFrameRecord.__table__],
            )
        self._ensure_video_caption_schema(video_database_url, self.video_engine)
        self._ensure_railway_labels_schema(database_url)

    def create_asset(self, asset: Asset) -> Asset:
        with self.session_factory.begin() as session:
            record = AssetRecord(
                id=asset.id,
                created_at=asset.created_at,
                payload=asset.model_dump(mode="json"),
            )
            session.merge(record)
        return asset

    def create_user(self, username: str, display_name: str, password_hash: str) -> AuthUser | None:
        normalized_username = username.strip().lower()
        with self.session_factory.begin() as session:
            if session.scalar(select(UserRecord).where(UserRecord.username == normalized_username)):
                return None
            role = "admin" if (session.scalar(select(func.count()).select_from(UserRecord)) or 0) == 0 else "student"
            user = AuthUser(username=normalized_username, displayName=display_name.strip(), role=role)
            session.add(
                UserRecord(
                    id=user.user_id,
                    username=user.username,
                    display_name=user.display_name,
                    password_hash=password_hash,
                    role=user.role,
                    is_active=user.is_active,
                    created_at=user.created_at,
                    updated_at=user.updated_at,
                )
            )
            return user

    def get_user_credentials(self, username: str) -> tuple[AuthUser, str] | None:
        with self.session_factory() as session:
            record = session.scalar(select(UserRecord).where(UserRecord.username == username.strip().lower()))
            if record is None:
                return None
            return self._auth_user_from_record(record), record.password_hash

    def create_auth_session(self, token_hash: str, user_id: str, expires_at: datetime) -> None:
        current = now_utc()
        with self.session_factory.begin() as session:
            session.add(
                AuthSessionRecord(
                    token_hash=token_hash,
                    user_id=user_id,
                    expires_at=expires_at,
                    created_at=current,
                    last_seen_at=current,
                )
            )

    def get_user_by_auth_session(self, token_hash: str) -> AuthUser | None:
        current = now_utc()
        with self.session_factory.begin() as session:
            auth_session = session.scalar(
                select(AuthSessionRecord).where(
                    AuthSessionRecord.token_hash == token_hash,
                    AuthSessionRecord.expires_at > current,
                )
            )
            if auth_session is None:
                expired_session = session.get(AuthSessionRecord, token_hash)
                if expired_session is not None:
                    session.delete(expired_session)
                return None
            user = session.get(UserRecord, auth_session.user_id)
            if user is None or not user.is_active:
                session.delete(auth_session)
                return None
            auth_session.last_seen_at = current
            return self._auth_user_from_record(user)

    def delete_auth_session(self, token_hash: str) -> None:
        with self.session_factory.begin() as session:
            record = session.get(AuthSessionRecord, token_hash)
            if record is not None:
                session.delete(record)

    def list_users(self) -> list[AuthUser]:
        with self.session_factory() as session:
            records = session.scalars(select(UserRecord).order_by(UserRecord.created_at.asc())).all()
            return [self._auth_user_from_record(record) for record in records]

    def update_user_role(self, user_id: str, role: str) -> AuthUser | None:
        with self.session_factory.begin() as session:
            record = session.get(UserRecord, user_id)
            if record is None:
                return None
            record.role = role
            record.updated_at = now_utc()
            return self._auth_user_from_record(record)

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

    def create_training_task(self, task: TrainingTask) -> TrainingTask:
        with self.session_factory.begin() as session:
            session.add(TrainingTaskRecord(
                id=task.training_id, name=task.name, task_type=task.task_type, model_name=task.model_name,
                status=task.status, train_image_ids=task.train_image_ids, val_image_ids=task.val_image_ids,
                epochs=task.epochs, batch_size=task.batch_size, image_size=task.image_size,
                dataset_dir=task.dataset_dir, output_dir=task.output_dir, error=task.error,
                best_model_path=task.best_model_path, created_at=task.created_at,
                started_at=task.started_at, finished_at=task.finished_at,
            ))
        return task

    def get_training_task(self, training_id: str) -> TrainingTask | None:
        with self.session_factory() as session:
            record = session.get(TrainingTaskRecord, training_id)
            return self._training_task_from_record(record) if record else None

    def list_training_tasks(self, limit: int = 50) -> list[TrainingTask]:
        with self.session_factory() as session:
            records = session.scalars(select(TrainingTaskRecord).order_by(TrainingTaskRecord.created_at.desc()).limit(limit)).all()
            return [self._training_task_from_record(record) for record in records]

    def update_training_task(self, training_id: str, **values) -> TrainingTask | None:
        with self.session_factory.begin() as session:
            record = session.get(TrainingTaskRecord, training_id)
            if record is None:
                return None
            for key, value in values.items():
                if hasattr(record, key):
                    setattr(record, key, value)
            return self._training_task_from_record(record)

    def save_training_metric(self, metric: TrainingMetric) -> TrainingMetric:
        with self.session_factory.begin() as session:
            session.add(TrainingMetricRecord(
                id=metric.metric_id, training_id=metric.training_id, epoch=metric.epoch,
                total_epochs=metric.total_epochs, train_loss=metric.train_loss, val_loss=metric.val_loss,
                precision=metric.precision, recall=metric.recall, map50=metric.map50,
                map50_95=metric.map50_95, learning_rate=metric.learning_rate, created_at=metric.created_at,
            ))
        return metric

    def list_training_metrics(self, training_id: str) -> list[TrainingMetric]:
        with self.session_factory() as session:
            records = session.scalars(select(TrainingMetricRecord).where(TrainingMetricRecord.training_id == training_id).order_by(TrainingMetricRecord.epoch.asc())).all()
            return [self._training_metric_from_record(record) for record in records]

    def delete_training_metrics(self, training_id: str) -> None:
        with self.session_factory.begin() as session:
            records = session.scalars(select(TrainingMetricRecord).where(TrainingMetricRecord.training_id == training_id)).all()
            for record in records:
                session.delete(record)

    def update_image_asset_file(self, image_id: str, original_name: str, file_name: str, file_path: str) -> ImageAsset | None:
        with self.session_factory.begin() as session:
            record = session.get(ImageAssetRecord, image_id)
            if record is None:
                return None
            record.original_name = original_name
            record.file_name = file_name
            record.file_path = file_path
            record.updated_at = now_utc()
            session.flush()
            return self._image_asset_from_record(record)

    def get_image_asset(self, image_id: str) -> ImageAsset | None:
        with self.session_factory() as session:
            record = session.get(ImageAssetRecord, image_id)
            return self._image_asset_from_record(record) if record else None

    def get_accessible_image_asset(self, image_id: str, user_id: str) -> ImageAsset | None:
        with self.session_factory() as session:
            record = session.scalar(
                select(ImageAssetRecord).where(
                    ImageAssetRecord.id == image_id,
                    or_(ImageAssetRecord.user_id == user_id, ImageAssetRecord.user_id.is_(None)),
                )
            )
            return self._image_asset_from_record(record) if record else None

    def delete_image_asset(self, image_id: str) -> list[str]:
        with self.session_factory.begin() as session:
            image = session.get(ImageAssetRecord, image_id)
            legacy_asset = session.get(AssetRecord, image_id)
            if image is None and legacy_asset is None:
                return []
            paths = [image.file_path] if image is not None else []
            if legacy_asset is not None:
                legacy_path = (legacy_asset.payload or {}).get("path")
                if legacy_path:
                    paths.append(legacy_path)
                annotation = session.get(AnnotationRecord, image_id)
                if annotation is not None:
                    session.delete(annotation)
                legacy_tasks = session.scalars(select(TaskRecord).where(TaskRecord.asset_id == image_id)).all()
                for task in legacy_tasks:
                    session.delete(task)
                session.delete(legacy_asset)
            tasks = session.scalars(select(ImageTaskRecord).where(ImageTaskRecord.image_id == image_id)).all()
            task_ids = [task.id for task in tasks]
            if task_ids:
                results = session.scalars(select(ImageTaskResultRecord).where(ImageTaskResultRecord.task_id.in_(task_ids))).all()
                for result in results:
                    if result.result_image_path:
                        paths.append(result.result_image_path)
                versions = session.scalars(
                    select(ImageTaskResultVersionRecord).where(ImageTaskResultVersionRecord.task_id.in_(task_ids))
                ).all()
                for version in versions:
                    if version.result_image_path:
                        paths.append(version.result_image_path)
                    session.delete(version)
                for result in results:
                    session.delete(result)
                for task in tasks:
                    session.delete(task)
            session.delete(image)
            return paths

    def list_image_assets(
        self,
        task_type: ImageTaskType | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
        query: str = "",
    ) -> tuple[list[ImageAsset], int]:
        offset = max(page - 1, 0) * page_size
        with self.session_factory() as session:
            base = select(ImageAssetRecord)
            count_query = select(func.count()).select_from(ImageAssetRecord)
            if session_id:
                base = base.where(ImageAssetRecord.session_id == session_id)
                count_query = count_query.where(ImageAssetRecord.session_id == session_id)
            if user_id:
                ownership = or_(ImageAssetRecord.user_id == user_id, ImageAssetRecord.user_id.is_(None))
                base = base.where(ownership)
                count_query = count_query.where(ownership)
            if query:
                pattern = f"%{query.strip()}%"
                name_filter = or_(ImageAssetRecord.original_name.ilike(pattern), ImageAssetRecord.file_name.ilike(pattern))
                base = base.where(name_filter)
                count_query = count_query.where(name_filter)
            base = base.order_by(ImageAssetRecord.created_at.desc())
            total = session.scalar(count_query)
            records = session.scalars(base).all() if task_type else session.scalars(base.offset(offset).limit(page_size)).all()
            images = [self._image_asset_from_record(record) for record in records]
            if task_type:
                image_ids = [image.image_id for image in images]
                task_records = session.scalars(
                    select(ImageTaskRecord).where(
                        ImageTaskRecord.image_id.in_(image_ids),
                        ImageTaskRecord.task_type == task_type,
                    )
                ).all() if image_ids else []
                task_map = {(record.image_id, record.session_id, record.user_key): record for record in task_records}
                result_records = session.scalars(
                    select(ImageTaskResultRecord).where(
                        ImageTaskResultRecord.task_id.in_([record.id for record in task_records])
                    )
                ).all() if task_records else []
                result_map = {record.task_id: record for record in result_records}
                ranked: list[tuple[int, ImageAsset]] = []
                for image in images:
                    task_user_id = None if image.session_id.startswith("video-import:") else image.user_id
                    task = task_map.get((image.image_id, image.session_id, task_user_id or ""))
                    result_record = result_map.get(task.id) if task else None
                    result = ImageTaskResult(
                        result_id=result_record.id,
                        task_id=result_record.task_id,
                        image_id=result_record.image_id,
                        task_type=result_record.task_type,
                        status=result_record.status,
                        result_json=result_record.result_json,
                        description_text=result_record.description_text,
                    ) if result_record else None
                    image.task_status = task.status if task else "idle"
                    image.has_current_task_result = result is not None
                    ranked.append((_task_result_count(task_type, result), image))
                ranked.sort(key=lambda item: (-item[0], -item[1].created_at.timestamp()))
                images = [image for _, image in ranked[offset : offset + page_size]]
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
        user_id: str | None = None,
    ) -> ImageTask | None:
        with self.session_factory() as session:
            record = session.scalar(
                select(ImageTaskRecord).where(
                    ImageTaskRecord.image_id == image_id,
                    ImageTaskRecord.task_type == task_type,
                    ImageTaskRecord.session_id == session_id,
                    ImageTaskRecord.user_key == (user_id or ""),
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
                record.review_status = "draft"
                record.reviewed_by = None
                record.reviewed_at = None
                record.review_comment = ""
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
        user_id: str | None = None,
    ) -> ImageTaskResult | None:
        with self.session_factory() as session:
            task = session.scalar(
                select(ImageTaskRecord).where(
                    ImageTaskRecord.image_id == image_id,
                    ImageTaskRecord.task_type == task_type,
                    ImageTaskRecord.session_id == session_id,
                    *([ImageTaskRecord.user_key == (user_id or "")] if user_id is not None else []),
                )
            )
            if not task:
                return None
            record = session.scalar(select(ImageTaskResultRecord).where(ImageTaskResultRecord.task_id == task.id))
            return self._image_task_result_from_record(record) if record else None

    def get_image_task_result_by_task_id(self, task_id: str) -> ImageTaskResult | None:
        with self.session_factory() as session:
            record = session.scalar(select(ImageTaskResultRecord).where(ImageTaskResultRecord.task_id == task_id))
            return self._image_task_result_from_record(record) if record else None

    def submit_image_task_result(self, task_id: str, user_id: str) -> ImageTaskResult | None:
        with self.session_factory.begin() as session:
            record = session.scalar(select(ImageTaskResultRecord).where(ImageTaskResultRecord.task_id == task_id))
            task = session.get(ImageTaskRecord, task_id)
            if (
                record is None
                or task is None
                or record.review_status not in {"draft", "rejected"}
                or (task.user_id is not None and task.user_id != user_id)
            ):
                return None
            record.review_status = "pending_review"
            record.submitted_by = user_id
            record.submitted_at = now_utc()
            record.reviewed_by = None
            record.reviewed_at = None
            record.review_comment = ""
            record.updated_at = now_utc()
            return self._image_task_result_from_record(record)

    def review_image_task_result(self, task_id: str, status: str, comment: str, reviewer_id: str) -> ImageTaskResult | None:
        with self.session_factory.begin() as session:
            record = session.scalar(select(ImageTaskResultRecord).where(ImageTaskResultRecord.task_id == task_id))
            if record is None or record.review_status != "pending_review" or record.submitted_by == reviewer_id:
                return None
            record.review_status = status
            record.reviewed_by = reviewer_id
            record.reviewed_at = now_utc()
            record.review_comment = comment.strip()
            record.updated_at = now_utc()
            return self._image_task_result_from_record(record)

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
            record.review_status = "draft"
            record.reviewed_by = None
            record.reviewed_at = None
            record.review_comment = ""
            record.updated_at = now_utc()
            return self._image_task_result_from_record(record)

    def list_image_task_result_versions(
        self,
        image_id: str,
        task_type: ImageTaskType,
        session_id: str = "default",
        user_id: str | None = None,
    ) -> list[ImageTaskResultVersion]:
        with self.session_factory() as session:
            task = session.scalar(
                select(ImageTaskRecord).where(
                    ImageTaskRecord.image_id == image_id,
                    ImageTaskRecord.task_type == task_type,
                    ImageTaskRecord.session_id == session_id,
                    *([ImageTaskRecord.user_key == (user_id or "")] if user_id is not None else []),
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

    def list_label_configs(self) -> list[LabelConfig]:
        with self.session_factory() as session:
            records = session.scalars(select(LabelConfigRecord).order_by(LabelConfigRecord.label_id.asc())).all()
            return [self._label_config_from_record(record) for record in records]

    def list_label_configs_page(self, page: int = 1, page_size: int = 20, query: str = "") -> tuple[list[LabelConfig], int]:
        offset = (page - 1) * page_size
        with self.session_factory() as session:
            statement = select(LabelConfigRecord)
            count_statement = select(func.count()).select_from(LabelConfigRecord)
            if query:
                pattern = f"%{query}%"
                condition = or_(
                    LabelConfigRecord.chinese_name.ilike(pattern),
                    LabelConfigRecord.english_name.ilike(pattern),
                    LabelConfigRecord.description.ilike(pattern),
                )
                statement = statement.where(condition)
                count_statement = count_statement.where(condition)
            records = session.scalars(statement.order_by(LabelConfigRecord.label_id.asc()).offset(offset).limit(page_size)).all()
            total = session.scalar(count_statement) or 0
            return [self._label_config_from_record(record) for record in records], int(total)

    def list_video_caption_descriptions(self) -> list[str]:
        with self.video_session_factory() as session:
            return list(session.scalars(
                select(VideoCaptionFrameRecord.description_text)
                .where(VideoCaptionFrameRecord.description_text != "")
            ).all())

    def update_label_thumbnail(self, label_id: int, thumbnail_url: str) -> LabelConfig | None:
        with self.session_factory.begin() as session:
            record = session.get(LabelConfigRecord, label_id)
            if record is None:
                return None
            record.thumbnail_url = thumbnail_url
            record.updated_at = now_utc()
            session.flush()
            return self._label_config_from_record(record)

    def create_label_config(
        self,
        english_name: str,
        chinese_name: str,
        description: str = "",
        copy_from_label_id: int | None = None,
    ) -> LabelConfig:
        with self.session_factory.begin() as session:
            if copy_from_label_id is not None:
                template = session.get(LabelConfigRecord, copy_from_label_id)
                if template:
                    english_name = english_name or f"{template.english_name}_copy"
                    chinese_name = chinese_name or f"{template.chinese_name}副本"
                    description = description or template.description
            next_id = session.scalar(select(func.coalesce(func.max(LabelConfigRecord.label_id), -1) + 1))
            now = now_utc()
            record = LabelConfigRecord(
                label_id=int(next_id or 0),
                english_name=english_name.strip(),
                chinese_name=chinese_name.strip(),
                description=description.strip(),
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.flush()
            return self._label_config_from_record(record)

    def copy_label_config(self, label_id: int) -> LabelConfig | None:
        with self.session_factory.begin() as session:
            template = session.get(LabelConfigRecord, label_id)
            if template is None:
                return None
            next_id = session.scalar(select(func.coalesce(func.max(LabelConfigRecord.label_id), -1) + 1))
            now = now_utc()
            record = LabelConfigRecord(
                label_id=int(next_id or 0),
                english_name=template.english_name,
                chinese_name=template.chinese_name,
                description=template.description,
                thumbnail_url=template.thumbnail_url,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.flush()
            return self._label_config_from_record(record)

    def update_label_config(
        self,
        label_id: int,
        english_name: str,
        chinese_name: str,
        description: str = "",
    ) -> LabelConfig | None:
        with self.session_factory.begin() as session:
            record = session.get(LabelConfigRecord, label_id)
            if record is None:
                return None
            record.english_name = english_name.strip()
            record.chinese_name = chinese_name.strip()
            record.description = description.strip()
            record.updated_at = now_utc()
            session.flush()
            return self._label_config_from_record(record)

    def delete_label_config(self, label_id: int) -> bool:
        with self.session_factory.begin() as session:
            record = session.get(LabelConfigRecord, label_id)
            if record is None:
                return False
            session.delete(record)
            return True

    def create_or_update_video_caption_batch(self, batch: VideoCaptionBatch) -> VideoCaptionBatch:
        with self.video_session_factory.begin() as session:
            record = session.scalar(select(VideoCaptionBatchRecord).where(VideoCaptionBatchRecord.name == batch.name))
            if record is None:
                record = self._video_caption_batch_record(batch)
                session.add(record)
            else:
                record.source_dir = batch.source_dir
                record.output_dir = batch.output_dir
                record.model_id = batch.model_id
                record.prompt = batch.prompt
                record.frame_interval_seconds = batch.frame_interval_seconds
                record.status = batch.status
                record.total_videos = batch.total_videos
                record.total_frames = batch.total_frames
                record.metadata_json = batch.metadata
                record.updated_at = now_utc()
                batch.batch_id = record.id
            session.flush()
            return self._video_caption_batch_from_record(record)

    def update_video_caption_batch_counts(self, batch_id: str, status: str | None = None) -> VideoCaptionBatch | None:
        with self.video_session_factory.begin() as session:
            record = session.get(VideoCaptionBatchRecord, batch_id)
            if record is None:
                return None
            record.total_videos = int(
                session.scalar(select(func.count()).select_from(VideoCaptionVideoRecord).where(VideoCaptionVideoRecord.batch_id == batch_id))
                or 0
            )
            record.total_frames = int(
                session.scalar(select(func.count()).select_from(VideoCaptionFrameRecord).where(VideoCaptionFrameRecord.batch_id == batch_id))
                or 0
            )
            if status:
                record.status = status
            record.updated_at = now_utc()
            session.flush()
            return self._video_caption_batch_from_record(record)

    def list_video_caption_batches(self) -> list[VideoCaptionBatch]:
        with self.video_session_factory() as session:
            records = session.scalars(select(VideoCaptionBatchRecord).order_by(VideoCaptionBatchRecord.updated_at.desc())).all()
            return [self._video_caption_batch_from_record(record) for record in records]

    def get_video_caption_batch(self, batch_id: str) -> VideoCaptionBatch | None:
        with self.video_session_factory() as session:
            record = session.get(VideoCaptionBatchRecord, batch_id)
            return self._video_caption_batch_from_record(record) if record else None

    def create_or_update_video_caption_video(self, video: VideoCaptionVideo) -> VideoCaptionVideo:
        with self.video_session_factory.begin() as session:
            record = session.scalar(
                select(VideoCaptionVideoRecord).where(
                    VideoCaptionVideoRecord.batch_id == video.batch_id,
                    VideoCaptionVideoRecord.source_path == video.source_path,
                )
                )
            if record is None:
                record = self._video_caption_video_record(video)
                session.add(record)
            else:
                record.filename = video.filename
                if video.display_name:
                    record.display_name = video.display_name
                if video.keywords:
                    record.keywords_json = video.keywords
                record.frame_dir = video.frame_dir
                record.fps = video.fps
                record.width = video.width
                record.height = video.height
                record.frame_count = video.frame_count
                record.duration_ms = video.duration_ms
                record.similar_frames_skipped = video.similar_frames_skipped
                record.status = video.status
                record.error = video.error
                record.updated_at = now_utc()
                video.video_id = record.id
            session.flush()
            return self._video_caption_video_from_record(record)

    def update_video_caption_video_summary(
        self,
        video_id: str,
        display_name: str,
        keywords: list[str],
    ) -> VideoCaptionVideo | None:
        with self.video_session_factory.begin() as session:
            record = session.get(VideoCaptionVideoRecord, video_id)
            if record is None:
                return None
            record.display_name = display_name.strip()
            record.keywords_json = keywords
            record.updated_at = now_utc()
            session.flush()
            return self._video_caption_video_from_record(record)

    def list_video_caption_videos(self, batch_id: str) -> list[VideoCaptionVideo]:
        with self.video_session_factory() as session:
            records = session.scalars(
                select(VideoCaptionVideoRecord)
                .where(VideoCaptionVideoRecord.batch_id == batch_id)
                .order_by(VideoCaptionVideoRecord.filename.asc())
            ).all()
            return [self._video_caption_video_from_record(record) for record in records]

    def get_video_caption_video(self, video_id: str) -> VideoCaptionVideo | None:
        with self.video_session_factory() as session:
            record = session.get(VideoCaptionVideoRecord, video_id)
            return self._video_caption_video_from_record(record) if record else None

    def save_video_caption_frame(self, frame: VideoCaptionFrame) -> VideoCaptionFrame:
        with self.video_session_factory.begin() as session:
            record = session.scalar(
                select(VideoCaptionFrameRecord).where(
                    VideoCaptionFrameRecord.video_id == frame.video_id,
                    VideoCaptionFrameRecord.frame_index == frame.frame_index,
                )
            )
            if record is None:
                record = self._video_caption_frame_record(frame)
                session.add(record)
            else:
                record.batch_id = frame.batch_id
                record.timestamp_ms = frame.timestamp_ms
                record.image_path = frame.image_path
                record.image_url = frame.image_url
                record.width = frame.width
                record.height = frame.height
                record.description_text = frame.description_text
                if frame.description_en:
                    # 解帧脚本重跑时不带译文，避免覆盖已有英文描述
                    record.description_en = frame.description_en
                record.model_id = frame.model_id
                record.status = frame.status
                record.error = frame.error
                record.result_json = frame.result_json
                record.updated_at = now_utc()
                frame.frame_id = record.id
            session.flush()
            return self._video_caption_frame_from_record(record)

    def update_video_caption_frame_description_en(self, frame_id: str, description_en: str) -> bool:
        with self.video_session_factory.begin() as session:
            record = session.get(VideoCaptionFrameRecord, frame_id)
            if record is None:
                return False
            record.description_en = description_en
            record.updated_at = now_utc()
            return True

    def update_video_caption_frame_review(
        self,
        frame_id: str,
        description_manual: str,
        safety_score: int | None,
    ) -> VideoCaptionFrame | None:
        with self.video_session_factory.begin() as session:
            record = session.get(VideoCaptionFrameRecord, frame_id)
            if record is None:
                return None
            record.description_manual = description_manual.strip()
            record.safety_score = safety_score
            record.updated_at = now_utc()
            session.flush()
            return self._video_caption_frame_from_record(record)

    def update_video_caption_frame_translation(self, frame_id: str, description_en: str) -> VideoCaptionFrame | None:
        with self.video_session_factory.begin() as session:
            record = session.get(VideoCaptionFrameRecord, frame_id)
            if record is None:
                return None
            record.description_en = description_en.strip()
            record.updated_at = now_utc()
            session.flush()
            return self._video_caption_frame_from_record(record)

    def list_video_caption_frames_missing_english(self, video_id: str) -> list[VideoCaptionFrame]:
        with self.video_session_factory() as session:
            records = session.scalars(
                select(VideoCaptionFrameRecord)
                .where(
                    VideoCaptionFrameRecord.video_id == video_id,
                    VideoCaptionFrameRecord.status == "success",
                    VideoCaptionFrameRecord.description_text != "",
                    or_(
                        VideoCaptionFrameRecord.description_en.is_(None),
                        VideoCaptionFrameRecord.description_en == "",
                    ),
                )
                .order_by(VideoCaptionFrameRecord.timestamp_ms.asc(), VideoCaptionFrameRecord.frame_index.asc())
            ).all()
            return [self._video_caption_frame_from_record(record) for record in records]

    def get_video_caption_frame(self, frame_id: str) -> VideoCaptionFrame | None:
        with self.video_session_factory() as session:
            record = session.get(VideoCaptionFrameRecord, frame_id)
            return self._video_caption_frame_from_record(record) if record else None

    def get_video_caption_frame_by_index(self, video_id: str, frame_index: int) -> VideoCaptionFrame | None:
        with self.video_session_factory() as session:
            record = session.scalar(
                select(VideoCaptionFrameRecord).where(
                    VideoCaptionFrameRecord.video_id == video_id,
                    VideoCaptionFrameRecord.frame_index == frame_index,
                )
            )
            return self._video_caption_frame_from_record(record) if record else None

    def list_video_caption_frames(
        self,
        video_id: str,
        page: int = 1,
        page_size: int = 100,
        query: str = "",
    ) -> tuple[list[VideoCaptionFrame], int]:
        offset = max(page - 1, 0) * page_size
        with self.video_session_factory() as session:
            statement = select(VideoCaptionFrameRecord).where(VideoCaptionFrameRecord.video_id == video_id)
            count_statement = select(func.count()).select_from(VideoCaptionFrameRecord).where(VideoCaptionFrameRecord.video_id == video_id)
            if query:
                pattern = f"%{query}%"
                condition = or_(
                    VideoCaptionFrameRecord.description_text.ilike(pattern),
                    VideoCaptionFrameRecord.description_en.ilike(pattern),
                    VideoCaptionFrameRecord.error.ilike(pattern),
                )
                statement = statement.where(condition)
                count_statement = count_statement.where(condition)
            records = session.scalars(
                statement.order_by(VideoCaptionFrameRecord.timestamp_ms.asc(), VideoCaptionFrameRecord.frame_index.asc())
                .offset(offset)
                .limit(page_size)
            ).all()
            total = session.scalar(count_statement)
            return [self._video_caption_frame_from_record(record) for record in records], int(total or 0)

    def close(self) -> None:
        self.engine.dispose()
        if self.video_engine is not self.engine:
            self.video_engine.dispose()

    def healthcheck(self) -> bool:
        with self.engine.connect() as connection:
            primary_ok = connection.execute(text("SELECT 1")).scalar_one() == 1
        if self.video_engine is self.engine:
            return primary_ok
        with self.video_engine.connect() as connection:
            return primary_ok and connection.execute(text("SELECT 1")).scalar_one() == 1

    def _ensure_label_config_schema(self, database_url: str) -> None:
        if not database_url.startswith("postgresql"):
            return
        with self.engine.begin() as connection:
            connection.execute(text("ALTER TABLE label_config DROP CONSTRAINT IF EXISTS label_config_english_name_key"))
            connection.execute(text("DROP INDEX IF EXISTS ix_label_config_english_name"))
            connection.execute(text("ALTER TABLE label_config ADD COLUMN IF NOT EXISTS thumbnail_url VARCHAR(1000) DEFAULT ''"))

    def _ensure_video_caption_schema(self, database_url: str, engine=None) -> None:
        if not database_url.startswith("postgresql"):
            return
        with (engine or self.engine).begin() as connection:
            connection.execute(text("ALTER TABLE video_caption_video ADD COLUMN IF NOT EXISTS display_name VARCHAR(500) DEFAULT ''"))
            connection.execute(text("ALTER TABLE video_caption_video ADD COLUMN IF NOT EXISTS keywords_json JSON DEFAULT '[]'::json"))
            connection.execute(text("ALTER TABLE video_caption_frame ADD COLUMN IF NOT EXISTS description_en TEXT DEFAULT ''"))
            connection.execute(text("ALTER TABLE video_caption_frame ADD COLUMN IF NOT EXISTS description_manual TEXT DEFAULT ''"))
            connection.execute(text("ALTER TABLE video_caption_frame ADD COLUMN IF NOT EXISTS safety_score INTEGER"))
            connection.execute(text("ALTER TABLE video_caption_video ADD COLUMN IF NOT EXISTS similar_frames_skipped INTEGER DEFAULT 0"))

    def _ensure_image_task_review_schema(self, database_url: str) -> None:
        if not database_url.startswith("postgresql"):
            return
        with self.engine.begin() as connection:
            connection.execute(text("ALTER TABLE image_task_result ADD COLUMN IF NOT EXISTS review_status VARCHAR(32) DEFAULT 'draft'"))
            connection.execute(text("ALTER TABLE image_task_result ADD COLUMN IF NOT EXISTS submitted_by VARCHAR(64)"))
            connection.execute(text("ALTER TABLE image_task_result ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ"))
            connection.execute(text("ALTER TABLE image_task_result ADD COLUMN IF NOT EXISTS reviewed_by VARCHAR(64)"))
            connection.execute(text("ALTER TABLE image_task_result ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ"))
            connection.execute(text("ALTER TABLE image_task_result ADD COLUMN IF NOT EXISTS review_comment TEXT DEFAULT ''"))

    def _ensure_railway_labels_schema(self, database_url: str) -> None:
        if not database_url.startswith("postgresql"):
            return
        with self.engine.begin() as connection:
            connection.execute(text("ALTER TABLE label_config DROP CONSTRAINT IF EXISTS label_config_english_name_key"))

    def _ensure_admin_user(self) -> None:
        with self.session_factory.begin() as session:
            has_admin = session.scalar(select(func.count()).select_from(UserRecord).where(UserRecord.role == "admin")) or 0
            if has_admin:
                return
            first_user = session.scalar(select(UserRecord).order_by(UserRecord.created_at.asc()).limit(1))
            if first_user is not None:
                first_user.role = "admin"
                first_user.updated_at = now_utc()

    def _seed_railway_labels(self, database_url: str) -> None:
        if not database_url.startswith("postgresql"):
            return
        presets = [
            ("rail", "钢轨", "Rails, stock rails, switch rails, guide rails, and rail-surface defects / 基本轨、尖轨、导轨及钢轨表面缺陷"),
            ("track", "轨道", "Track, sleepers, and ballast-bed areas / 线路、轨枕和道床范围"),
            ("sleeper", "轨枕", "Concrete or timber sleepers / 混凝土或木质轨枕"),
            ("ballast", "道砟", "Ballast stones, including missing or contaminated areas / 道床碎石及缺失、污染区域"),
            ("fastener", "扣件", "Rail clips, bolts, baseplates, and other fastening components / 弹条、螺栓、垫板等扣件组件"),
            ("rail_joint", "钢轨接头", "Rail joints, fishplates, and connecting bolts / 接头、夹板及连接螺栓"),
            ("switch", "道岔", "Switch machines, switch rails, frogs, and connecting rods / 转辙器、尖轨、辙叉及连接杆"),
            ("crossing", "平交道口", "Rail-road crossings and associated facilities / 铁路与道路平交区域及设施"),
            ("platform", "站台", "Platform edges, screen doors, and waiting areas / 站台边缘、屏蔽门及候车区域"),
            ("railway_vehicle", "铁路车辆", "Locomotives, passenger and freight cars, and rail-maintenance vehicles / 机车、客车、货车及轨道工程车辆"),
            ("train", "列车", "A complete train or train consist / 完整列车或列车编组"),
            ("railway_worker", "铁路工作人员", "Inspection, maintenance, dispatch, and construction personnel / 巡检、维修、调度和施工人员"),
            ("passenger", "乘客", "Passengers on platforms or inside rail cars / 站台及车厢内乘客"),
            ("helmet", "安全帽", "Head-protection equipment worn by personnel / 人员头部安全防护用品"),
            ("safety_vest", "反光背心", "High-visibility protective clothing for railway work / 铁路作业反光防护服"),
            ("signal", "铁路信号", "Signals, signal lights, and displayed aspects / 信号机、信号灯及显示状态"),
            ("railway_sign", "铁路标志", "Mileage, speed-limit, warning, and route signs / 里程、限速、警示和线路标志"),
            ("catenary", "接触网", "Contact wires, messenger wires, droppers, and masts / 接触线、承力索、吊弦及支柱"),
            ("pantograph", "受电弓", "Pantographs on locomotives or multiple units and their condition / 机车或动车组受电弓及其状态"),
            ("overhead_line", "架空线", "Overhead railway power and communication lines / 铁路供电及通信架空线路"),
            ("obstacle", "侵限障碍物", "Foreign objects or obstacles entering the railway clearance envelope / 进入线路限界的异物或障碍物"),
            ("crack", "裂纹", "Surface cracks in rails, sleepers, or structures / 钢轨、轨枕、构件表面裂纹"),
            ("wear", "磨耗", "Abnormal wear on rails or railway components / 钢轨及铁路构件异常磨损"),
            ("corrosion", "锈蚀", "Corrosion on rails, fasteners, or metal components / 钢轨、扣件及金属构件腐蚀"),
            ("deformation", "变形", "Abnormal bending or twisting of track geometry or components / 轨道几何或构件异常弯曲、扭曲"),
            ("missing_fastener", "扣件缺失", "Missing or detached fastening components / 扣件组件缺失或脱落"),
            ("loose_fastener", "扣件松动", "Untightened fasteners or fasteners in abnormal positions / 扣件未紧固或位置异常"),
            ("water", "积水", "Standing water on tracks, in tunnels, or in rail yards / 线路、隧道或站场积水"),
            ("smoke", "烟雾", "Abnormal smoke from trains, tunnels, or railway facilities / 列车、隧道或设施异常烟雾"),
            ("fire", "火情", "Open flames or suspected fire areas / 明火或疑似燃烧区域"),
            ("animal", "动物", "Animals entering railway track areas / 进入铁路线路区域的动物"),
        ]
        with self.session_factory.begin() as session:
            existing_records = session.scalars(select(LabelConfigRecord)).all()
            existing = {record.english_name: record for record in existing_records}
            next_id = int(session.scalar(select(func.coalesce(func.max(LabelConfigRecord.label_id), -1) + 1)) or 0)
            now = now_utc()
            for english_name, chinese_name, description in presets:
                if english_name in existing:
                    existing[english_name].description = description
                    existing[english_name].updated_at = now
                    continue
                session.add(LabelConfigRecord(
                    label_id=next_id,
                    english_name=english_name,
                    chinese_name=chinese_name,
                    description=description,
                    created_at=now,
                    updated_at=now,
                ))
                next_id += 1

    def _task_record(self, task: DetectTask) -> TaskRecord:
        return TaskRecord(
            id=task.id,
            asset_id=task.asset_id,
            status=task.status,
            created_at=task.created_at,
            payload=task.model_dump(mode="json"),
        )

    def _auth_user_from_record(self, record: UserRecord) -> AuthUser:
        return AuthUser(
            userId=record.id,
            username=record.username,
            displayName=record.display_name,
            role=record.role,
            isActive=record.is_active,
            createdAt=record.created_at,
            updatedAt=record.updated_at,
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

    def _training_task_from_record(self, record: TrainingTaskRecord) -> TrainingTask:
        return TrainingTask(
            training_id=record.id, name=record.name, task_type=record.task_type, model_name=record.model_name,
            status=record.status, train_image_ids=record.train_image_ids or [], val_image_ids=record.val_image_ids or [],
            epochs=record.epochs, batch_size=record.batch_size, image_size=record.image_size,
            dataset_dir=record.dataset_dir, output_dir=record.output_dir, error=record.error,
            best_model_path=record.best_model_path, created_at=record.created_at,
            started_at=record.started_at, finished_at=record.finished_at,
        )

    def _training_metric_from_record(self, record: TrainingMetricRecord) -> TrainingMetric:
        return TrainingMetric(
            metric_id=record.id, training_id=record.training_id, epoch=record.epoch,
            total_epochs=record.total_epochs, train_loss=record.train_loss, val_loss=record.val_loss,
            precision=record.precision, recall=record.recall, map50=record.map50,
            map50_95=record.map50_95, learning_rate=record.learning_rate, created_at=record.created_at,
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
            review_status=result.review_status,
            submitted_by=result.submitted_by,
            submitted_at=result.submitted_at,
            reviewed_by=result.reviewed_by,
            reviewed_at=result.reviewed_at,
            review_comment=result.review_comment,
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
            source=latest.source if latest else "ai",
            model_id=latest.model_id if latest else "",
            review_status=record.review_status or "draft",
            submitted_by=record.submitted_by,
            submitted_at=record.submitted_at,
            reviewed_by=record.reviewed_by,
            reviewed_at=record.reviewed_at,
            review_comment=record.review_comment or "",
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

    def _label_config_from_record(self, record: LabelConfigRecord) -> LabelConfig:
        return LabelConfig(
            label_id=record.label_id,
            english_name=record.english_name,
            chinese_name=record.chinese_name,
            description=record.description,
            thumbnail_url=record.thumbnail_url or "",
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _video_caption_batch_record(self, batch: VideoCaptionBatch) -> VideoCaptionBatchRecord:
        return VideoCaptionBatchRecord(
            id=batch.batch_id,
            name=batch.name,
            source_dir=batch.source_dir,
            output_dir=batch.output_dir,
            model_id=batch.model_id,
            prompt=batch.prompt,
            frame_interval_seconds=batch.frame_interval_seconds,
            status=batch.status,
            total_videos=batch.total_videos,
            total_frames=batch.total_frames,
            metadata_json=batch.metadata,
            created_at=batch.created_at,
            updated_at=batch.updated_at,
        )

    def _video_caption_batch_from_record(self, record: VideoCaptionBatchRecord) -> VideoCaptionBatch:
        return VideoCaptionBatch(
            batch_id=record.id,
            name=record.name,
            source_dir=record.source_dir,
            output_dir=record.output_dir,
            model_id=record.model_id,
            prompt=record.prompt,
            frame_interval_seconds=record.frame_interval_seconds,
            status=record.status,
            total_videos=record.total_videos,
            total_frames=record.total_frames,
            metadata=record.metadata_json or {},
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _video_caption_video_record(self, video: VideoCaptionVideo) -> VideoCaptionVideoRecord:
        return VideoCaptionVideoRecord(
            id=video.video_id,
            batch_id=video.batch_id,
            filename=video.filename,
            display_name=video.display_name,
            keywords_json=video.keywords,
            source_path=video.source_path,
            frame_dir=video.frame_dir,
            fps=video.fps,
            width=video.width,
            height=video.height,
            frame_count=video.frame_count,
            duration_ms=video.duration_ms,
            similar_frames_skipped=video.similar_frames_skipped,
            status=video.status,
            error=video.error,
            created_at=video.created_at,
            updated_at=video.updated_at,
        )

    def _video_caption_video_from_record(self, record: VideoCaptionVideoRecord) -> VideoCaptionVideo:
        return VideoCaptionVideo(
            video_id=record.id,
            batch_id=record.batch_id,
            filename=record.filename,
            display_name=record.display_name,
            keywords=list(record.keywords_json or []),
            source_path=record.source_path,
            frame_dir=record.frame_dir,
            fps=record.fps,
            width=record.width,
            height=record.height,
            frame_count=record.frame_count,
            duration_ms=record.duration_ms,
            similar_frames_skipped=record.similar_frames_skipped or 0,
            status=record.status,
            error=record.error,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _video_caption_frame_record(self, frame: VideoCaptionFrame) -> VideoCaptionFrameRecord:
        return VideoCaptionFrameRecord(
            id=frame.frame_id,
            batch_id=frame.batch_id,
            video_id=frame.video_id,
            frame_index=frame.frame_index,
            timestamp_ms=frame.timestamp_ms,
            image_path=frame.image_path,
            image_url=frame.image_url,
            width=frame.width,
            height=frame.height,
            description_text=frame.description_text,
            description_en=frame.description_en,
            model_id=frame.model_id,
            status=frame.status,
            error=frame.error,
            result_json=frame.result_json,
            created_at=frame.created_at,
            updated_at=frame.updated_at,
        )

    def _video_caption_frame_from_record(self, record: VideoCaptionFrameRecord) -> VideoCaptionFrame:
        return VideoCaptionFrame(
            frame_id=record.id,
            batch_id=record.batch_id,
            video_id=record.video_id,
            frame_index=record.frame_index,
            timestamp_ms=record.timestamp_ms,
            image_path=record.image_path,
            image_url=record.image_url,
            width=record.width,
            height=record.height,
            description_text=record.description_text,
            description_en=record.description_en or "",
            description_manual=record.description_manual or "",
            safety_score=record.safety_score,
            model_id=record.model_id,
            status=record.status,
            error=record.error,
            result_json=record.result_json or {},
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
