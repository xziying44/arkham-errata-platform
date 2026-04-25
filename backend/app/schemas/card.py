"""卡牌 API 的 Pydantic 模式定义"""

from pydantic import BaseModel, ConfigDict
from typing import Optional


class CardIndexResponse(BaseModel):
    """卡牌索引响应"""
    model_config = ConfigDict(from_attributes=True)

    arkhamdb_id: str
    name_zh: str
    name_en: str
    category: str
    cycle: str
    expansion: str
    is_double_sided: bool
    mapping_status: str


class LocalCardFileResponse(BaseModel):
    """本地 .card 文件响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    arkhamdb_id: str
    face: str
    relative_path: str
    content_hash: str
    last_modified: str


class TTSCardImageResponse(BaseModel):
    """TTS 卡牌图片响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    arkhamdb_id: str
    source: str
    relative_json_path: str
    card_id: int
    deck_key: str
    face_url: str
    back_url: str
    grid_width: int
    grid_height: int
    grid_position: int
    unique_back: bool
    cached_front_path: str | None
    cached_back_path: str | None
    shared_back_id: int | None


class CardDetailResponse(BaseModel):
    """卡牌详情响应"""
    index: CardIndexResponse
    local_files: list[LocalCardFileResponse]
    tts_en: Optional[TTSCardImageResponse] = None
    tts_zh: Optional[TTSCardImageResponse] = None
