from sqlalchemy import String, Integer, Boolean, ForeignKey, Enum as SAEnum, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
import enum


class MappingStatus(str, enum.Enum):
    CONFIRMED = "已确认"
    PENDING = "待确认"
    ERROR = "映射异常"


class CardIndex(Base):
    __tablename__ = "card_index"

    arkhamdb_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name_zh: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    name_en: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    cycle: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    expansion: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    is_double_sided: Mapped[bool] = mapped_column(Boolean, default=False)
    mapping_status: Mapped[MappingStatus] = mapped_column(
        SAEnum(MappingStatus), default=MappingStatus.PENDING
    )


class LocalCardFile(Base):
    __tablename__ = "local_card_files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    arkhamdb_id: Mapped[str] = mapped_column(String(16), ForeignKey("card_index.arkhamdb_id"), nullable=False, index=True)
    face: Mapped[str] = mapped_column(String(4), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    last_modified: Mapped[str] = mapped_column(String(32), nullable=False, default="")


class SharedCardBack(Base):
    __tablename__ = "shared_card_backs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    back_url: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(8), nullable=False)


class TTSCardImage(Base):
    __tablename__ = "tts_card_images"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    arkhamdb_id: Mapped[str] = mapped_column(String(16), ForeignKey("card_index.arkhamdb_id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(8), nullable=False)
    relative_json_path: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    card_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deck_key: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    face_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    back_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    grid_width: Mapped[int] = mapped_column(Integer, default=10)
    grid_height: Mapped[int] = mapped_column(Integer, default=1)
    grid_position: Mapped[int] = mapped_column(Integer, default=0)
    unique_back: Mapped[bool] = mapped_column(Boolean, default=False)
    cached_front_path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    cached_back_path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    shared_back_id: Mapped[int | None] = mapped_column(ForeignKey("shared_card_backs.id"), nullable=True)
