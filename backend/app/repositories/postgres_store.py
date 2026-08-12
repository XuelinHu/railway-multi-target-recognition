from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint, create_engine, func, or_, select, text
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
    model_id: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PostgresStore:
    def __init__(self, database_url: str) -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        self._ensure_label_config_schema(database_url)
        self._ensure_video_caption_schema(database_url)
        self._ensure_image_task_review_schema(database_url)
        self._ensure_admin_user()

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

    def list_image_assets(
        self,
        task_type: ImageTaskType | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
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
            base = base.order_by(ImageAssetRecord.created_at.desc())
            records = session.scalars(base.offset(offset).limit(page_size)).all()
            total = session.scalar(count_query)
            images = [self._image_asset_from_record(record) for record in records]
            if task_type:
                for image in images:
                    task = self.get_image_task(image.image_id, task_type, image.session_id)
                    result = self.get_image_task_result(image.image_id, task_type, image.session_id)
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

    def list_label_configs(self) -> list[LabelConfig]:
        with self.session_factory() as session:
            records = session.scalars(select(LabelConfigRecord).order_by(LabelConfigRecord.label_id.asc())).all()
            return [self._label_config_from_record(record) for record in records]

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
        with self.session_factory.begin() as session:
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
        with self.session_factory.begin() as session:
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
        with self.session_factory() as session:
            records = session.scalars(select(VideoCaptionBatchRecord).order_by(VideoCaptionBatchRecord.updated_at.desc())).all()
            return [self._video_caption_batch_from_record(record) for record in records]

    def get_video_caption_batch(self, batch_id: str) -> VideoCaptionBatch | None:
        with self.session_factory() as session:
            record = session.get(VideoCaptionBatchRecord, batch_id)
            return self._video_caption_batch_from_record(record) if record else None

    def create_or_update_video_caption_video(self, video: VideoCaptionVideo) -> VideoCaptionVideo:
        with self.session_factory.begin() as session:
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
        with self.session_factory.begin() as session:
            record = session.get(VideoCaptionVideoRecord, video_id)
            if record is None:
                return None
            record.display_name = display_name.strip()
            record.keywords_json = keywords
            record.updated_at = now_utc()
            session.flush()
            return self._video_caption_video_from_record(record)

    def list_video_caption_videos(self, batch_id: str) -> list[VideoCaptionVideo]:
        with self.session_factory() as session:
            records = session.scalars(
                select(VideoCaptionVideoRecord)
                .where(VideoCaptionVideoRecord.batch_id == batch_id)
                .order_by(VideoCaptionVideoRecord.filename.asc())
            ).all()
            return [self._video_caption_video_from_record(record) for record in records]

    def get_video_caption_video(self, video_id: str) -> VideoCaptionVideo | None:
        with self.session_factory() as session:
            record = session.get(VideoCaptionVideoRecord, video_id)
            return self._video_caption_video_from_record(record) if record else None

    def save_video_caption_frame(self, frame: VideoCaptionFrame) -> VideoCaptionFrame:
        with self.session_factory.begin() as session:
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
                record.model_id = frame.model_id
                record.status = frame.status
                record.error = frame.error
                record.result_json = frame.result_json
                record.updated_at = now_utc()
                frame.frame_id = record.id
            session.flush()
            return self._video_caption_frame_from_record(record)

    def get_video_caption_frame(self, frame_id: str) -> VideoCaptionFrame | None:
        with self.session_factory() as session:
            record = session.get(VideoCaptionFrameRecord, frame_id)
            return self._video_caption_frame_from_record(record) if record else None

    def get_video_caption_frame_by_index(self, video_id: str, frame_index: int) -> VideoCaptionFrame | None:
        with self.session_factory() as session:
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
        with self.session_factory() as session:
            statement = select(VideoCaptionFrameRecord).where(VideoCaptionFrameRecord.video_id == video_id)
            count_statement = select(func.count()).select_from(VideoCaptionFrameRecord).where(VideoCaptionFrameRecord.video_id == video_id)
            if query:
                pattern = f"%{query}%"
                condition = or_(
                    VideoCaptionFrameRecord.description_text.ilike(pattern),
                    VideoCaptionFrameRecord.error.ilike(pattern),
                )
                statement = statement.where(condition)
                count_statement = count_statement.where(condition)
            records = session.scalars(
                statement.order_by(VideoCaptionFrameRecord.frame_index.asc()).offset(offset).limit(page_size)
            ).all()
            total = session.scalar(count_statement)
            return [self._video_caption_frame_from_record(record) for record in records], int(total or 0)

    def close(self) -> None:
        self.engine.dispose()

    def healthcheck(self) -> bool:
        with self.engine.connect() as connection:
            return connection.execute(text("SELECT 1")).scalar_one() == 1

    def _ensure_label_config_schema(self, database_url: str) -> None:
        if not database_url.startswith("postgresql"):
            return
        with self.engine.begin() as connection:
            connection.execute(text("ALTER TABLE label_config DROP CONSTRAINT IF EXISTS label_config_english_name_key"))
            connection.execute(text("DROP INDEX IF EXISTS ix_label_config_english_name"))

    def _ensure_video_caption_schema(self, database_url: str) -> None:
        if not database_url.startswith("postgresql"):
            return
        with self.engine.begin() as connection:
            connection.execute(text("ALTER TABLE video_caption_video ADD COLUMN IF NOT EXISTS display_name VARCHAR(500) DEFAULT ''"))
            connection.execute(text("ALTER TABLE video_caption_video ADD COLUMN IF NOT EXISTS keywords_json JSON DEFAULT '[]'::json"))

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

    def _ensure_admin_user(self) -> None:
        with self.session_factory.begin() as session:
            has_admin = session.scalar(select(func.count()).select_from(UserRecord).where(UserRecord.role == "admin")) or 0
            if has_admin:
                return
            first_user = session.scalar(select(UserRecord).order_by(UserRecord.created_at.asc()).limit(1))
            if first_user is not None:
                first_user.role = "admin"
                first_user.updated_at = now_utc()

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
            model_id=record.model_id,
            status=record.status,
            error=record.error,
            result_json=record.result_json or {},
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
