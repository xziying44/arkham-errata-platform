"""勘误 API 的 Pydantic 模式定义"""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ErrataSubmitRequest(BaseModel):
    """勘误提交请求"""
    arkhamdb_id: str
    original_content: dict
    modified_content: dict


class ErrataResponse(BaseModel):
    """勘误列表项响应"""
    model_config = {"from_attributes": True}

    id: int
    arkhamdb_id: str
    user_id: int
    status: str
    review_note: str | None
    batch_id: str | None
    created_at: datetime
    updated_at: datetime


class ErrataDetailResponse(ErrataResponse):
    """勘误详情响应（包含原始/修改后内容及渲染预览）"""
    original_content: dict
    modified_content: dict
    rendered_preview: str | None
