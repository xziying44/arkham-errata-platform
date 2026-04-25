from sqlalchemy import String, Integer, ForeignKey, Enum as SAEnum, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.database import Base
import enum


class ErrataStatus(str, enum.Enum):
    PENDING = "待审核"
    APPROVED = "已通过"
    REJECTED = "已驳回"


class Errata(Base):
    __tablename__ = "errata"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    arkhamdb_id: Mapped[str] = mapped_column(String(16), ForeignKey("card_index.arkhamdb_id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    original_content: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    modified_content: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[ErrataStatus] = mapped_column(
        SAEnum(ErrataStatus), default=ErrataStatus.PENDING, nullable=False
    )
    reviewer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    review_note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    batch_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    rendered_preview: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
