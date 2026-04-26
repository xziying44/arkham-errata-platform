"""卡牌 API 的 Pydantic 模式定义"""

from pydantic import BaseModel, ConfigDict
from typing import Any, Optional


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


class TTSImageMappingResponse(BaseModel):
    """本地 .card 面到 TTS 卡图面的解析结果"""
    local_face: str
    source: str
    tts_id: int | None
    tts_side: str
    image_url: str | None
    status: str
    relative_json_path: str | None = None
    card_id: int | None = None


class CardDetailResponse(BaseModel):
    """卡牌详情响应"""
    index: CardIndexResponse
    local_files: list[LocalCardFileResponse]
    tts_en: list[TTSCardImageResponse] = []
    tts_zh: list[TTSCardImageResponse] = []
    image_mappings: list[TTSImageMappingResponse] = []
    is_single_sided: bool = False
    back_overrides: dict[str, Any] = {}
