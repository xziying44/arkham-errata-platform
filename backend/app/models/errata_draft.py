import enum
from datetime import datetime
from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ErrataDraftStatus(str, enum.Enum):
    ERRATA = "勘误"
    WAITING_PUBLISH = "待发布"
    ARCHIVED = "已归档"


class ErrataAuditAction(str, enum.Enum):
    CREATE = "创建副本"
    SAVE = "保存勘误"
    REVIEW_SAVE = "审核修改"
    PACKAGE = "生成包"
    UNLOCK = "解锁退回"
    CANCEL = "取消勘误"
    PUBLISH = "发布完成"


class ErrataPackageStatus(str, enum.Enum):
    WAITING_PUBLISH = "待发布"
    PUBLISHING = "发布中"
    PUBLISHED = "已发布"
    UNLOCKED = "已退回"


class ErrataDraft(Base):
    __tablename__ = "errata_drafts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    arkhamdb_id: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[ErrataDraftStatus] = mapped_column(
        SAEnum(ErrataDraftStatus), default=ErrataDraftStatus.ERRATA, nullable=False, index=True
    )
    original_faces: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    modified_faces: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    changed_faces: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    rendered_previews: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    package_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("errata_packages.id"), nullable=True, index=True)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    updated_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ErrataAuditLog(Base):
    __tablename__ = "errata_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    draft_id: Mapped[int] = mapped_column(Integer, ForeignKey("errata_drafts.id"), nullable=False, index=True)
    arkhamdb_id: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action: Mapped[ErrataAuditAction] = mapped_column(SAEnum(ErrataAuditAction), nullable=False, index=True)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    changed_faces: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    diff_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ErrataPackage(Base):
    __tablename__ = "errata_packages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    package_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    status: Mapped[ErrataPackageStatus] = mapped_column(SAEnum(ErrataPackageStatus), nullable=False, index=True)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    published_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    unlocked_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PublishSessionStatus(str, enum.Enum):
    DRAFT = "草稿"
    GENERATING = "生成中"
    SHEETS_READY = "待确认精灵图"
    URLS_READY = "待准备URL"
    PATCH_READY = "待导出补丁"
    COMPLETED = "已完成"
    SUPERSEDED = "已废弃"
    FAILED = "失败"


class PublishArtifactKind(str, enum.Enum):
    CARD_IMAGE = "card_image"
    SHEET_FRONT = "sheet_front"
    SHEET_BACK = "sheet_back"
    TTS_BAG = "tts_bag"
    URL_MAPPING = "url_mapping"
    PATCH_ZIP = "patch_zip"
    MANIFEST = "manifest"
    REPORT = "report"


class PublishArtifactStatus(str, enum.Enum):
    ACTIVE = "active"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"
    DELETED = "deleted"
    FAILED = "failed"


class PublishDirectoryTargetArea(str, enum.Enum):
    CAMPAIGNS = "campaigns"
    PLAYER_CARDS = "player_cards"


class PublishSession(Base):
    __tablename__ = "publish_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    package_id: Mapped[int] = mapped_column(Integer, ForeignKey("errata_packages.id"), nullable=False, index=True)
    status: Mapped[PublishSessionStatus] = mapped_column(SAEnum(PublishSessionStatus), nullable=False, index=True)
    current_step: Mapped[str] = mapped_column(String(64), nullable=False, default="select_package")
    artifact_root: Mapped[str] = mapped_column(String(512), nullable=False)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    updated_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cleanup_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class PublishArtifact(Base):
    __tablename__ = "publish_artifacts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("publish_sessions.id"), nullable=False, index=True)
    kind: Mapped[PublishArtifactKind] = mapped_column(SAEnum(PublishArtifactKind), nullable=False, index=True)
    status: Mapped[PublishArtifactStatus] = mapped_column(SAEnum(PublishArtifactStatus), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    public_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    artifact_metadata: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class PublishDirectoryPreset(Base):
    __tablename__ = "publish_directory_presets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    local_dir_prefix: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    target_area: Mapped[PublishDirectoryTargetArea] = mapped_column(SAEnum(PublishDirectoryTargetArea), nullable=False, index=True)
    target_bag_path: Mapped[str] = mapped_column(String(512), nullable=False)
    target_bag_guid: Mapped[str] = mapped_column(String(16), nullable=False)
    target_object_dir: Mapped[str] = mapped_column(String(256), nullable=False)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
