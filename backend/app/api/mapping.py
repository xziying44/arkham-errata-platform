"""管理员卡图映射管理 API。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_admin
from app.database import get_db
from app.models.card import LocalCardFile, TTSCardImage
from app.models.user import User
from app.schemas.card import LocalCardFileResponse, TTSCardImageResponse
from app.services.mapping_index import (
    bind_mapping,
    clear_back_override,
    confirm_card_mapping,
    get_card_back_presets,
    get_mapping_detail,
    resolve_card_image_mappings,
    search_tts_candidates,
    set_back_override,
    swap_source_faces,
    unbind_mapping,
)

router = APIRouter(prefix="/api/admin/mapping", tags=["映射管理"])


class BindMappingRequest(BaseModel):
    arkhamdb_id: str
    local_face: str
    source: str
    tts_id: int
    tts_side: str


class UnbindMappingRequest(BaseModel):
    arkhamdb_id: str
    local_face: str
    source: str


class SwapMappingRequest(BaseModel):
    arkhamdb_id: str
    source: str


class ConfirmMappingRequest(BaseModel):
    arkhamdb_id: str


class BackOverrideRequest(BaseModel):
    preset_key: str


def _serialize_mapping_detail(detail: dict):
    card = detail["card"]
    return {
        "arkhamdb_id": detail["arkhamdb_id"],
        "card": {
            "arkhamdb_id": card.arkhamdb_id,
            "name_zh": card.name_zh,
            "name_en": card.name_en,
            "category": card.category,
            "cycle": card.cycle,
            "expansion": card.expansion,
            "is_double_sided": card.is_double_sided,
            "mapping_status": card.mapping_status.value,
        } if card else None,
        "local_files": [LocalCardFileResponse.model_validate(item).model_dump() for item in detail["local_files"]],
        "is_single_sided": detail["is_single_sided"],
        "back_overrides": detail["back_overrides"],
        "image_mappings": detail["image_mappings"],
        "confirmed": detail["confirmed"],
        "confirmed_by": detail["confirmed_by"],
        "confirmed_at": detail["confirmed_at"],
        "index_path": detail["index_path"],
    }


def _is_single_sided(local_files: list[LocalCardFile]) -> bool:
    return len(local_files) == 1


async def _get_local_files_or_404(db: AsyncSession, arkhamdb_id: str) -> list[LocalCardFile]:
    result = await db.execute(
        select(LocalCardFile)
        .where(LocalCardFile.arkhamdb_id == arkhamdb_id)
        .order_by(LocalCardFile.face)
    )
    files = list(result.scalars().all())
    if not files:
        raise HTTPException(status_code=404, detail="本地卡牌不存在")
    return files


@router.get("/back-presets")
async def get_back_presets(admin: User = Depends(require_admin)):
    return {"items": get_card_back_presets()}


@router.post("/{arkhamdb_id}/faces/{face}/back-override")
async def save_back_override(
    arkhamdb_id: str,
    face: str,
    req: BackOverrideRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    local_files = await _get_local_files_or_404(db, arkhamdb_id)
    if face not in {item.face for item in local_files}:
        raise HTTPException(status_code=404, detail="本地卡牌面不存在")
    try:
        set_back_override(arkhamdb_id, face, req.preset_key, admin.username, _is_single_sided(local_files))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize_mapping_detail(await get_mapping_detail(db, arkhamdb_id))


@router.delete("/{arkhamdb_id}/faces/{face}/back-override")
async def delete_back_override(
    arkhamdb_id: str,
    face: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    local_files = await _get_local_files_or_404(db, arkhamdb_id)
    if face not in {item.face for item in local_files}:
        raise HTTPException(status_code=404, detail="本地卡牌面不存在")
    try:
        clear_back_override(arkhamdb_id, face, _is_single_sided(local_files))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize_mapping_detail(await get_mapping_detail(db, arkhamdb_id))


@router.get("/{arkhamdb_id}")
async def get_admin_mapping_detail(
    arkhamdb_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    detail = await get_mapping_detail(db, arkhamdb_id)
    if not detail["card"] or not detail["local_files"]:
        raise HTTPException(status_code=404, detail="本地卡牌不存在")
    return _serialize_mapping_detail(detail)


@router.get("/search/tts")
async def search_tts(
    source: str | None = None,
    keyword: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    items = await search_tts_candidates(db, source, keyword, limit)
    return {"items": [TTSCardImageResponse.model_validate(item).model_dump() for item in items]}


@router.post("/bind")
async def bind_tts_mapping(
    req: BindMappingRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    tts_image = await db.get(TTSCardImage, req.tts_id)
    if not tts_image:
        raise HTTPException(status_code=404, detail="TTS 卡图不存在")
    if tts_image.source != req.source:
        raise HTTPException(status_code=400, detail="TTS 卡图来源与绑定槽位不一致")
    local = await db.execute(
        select(LocalCardFile).where(
            LocalCardFile.arkhamdb_id == req.arkhamdb_id,
            LocalCardFile.face == req.local_face,
        )
    )
    if not local.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="本地卡牌面不存在")
    try:
        bind_mapping(req.arkhamdb_id, req.local_face, req.source, req.tts_id, req.tts_side, admin.username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"image_mappings": await resolve_card_image_mappings(db, req.arkhamdb_id)}


@router.post("/unbind")
async def unbind_tts_mapping(
    req: UnbindMappingRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    unbind_mapping(req.arkhamdb_id, req.local_face, req.source)
    return {"image_mappings": await resolve_card_image_mappings(db, req.arkhamdb_id)}


@router.post("/swap")
async def swap_tts_mapping(
    req: SwapMappingRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    try:
        swap_source_faces(req.arkhamdb_id, req.source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"image_mappings": await resolve_card_image_mappings(db, req.arkhamdb_id)}


@router.post("/confirm")
async def confirm_tts_mapping(
    req: ConfirmMappingRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    confirm_card_mapping(req.arkhamdb_id, admin.username)
    return _serialize_mapping_detail(await get_mapping_detail(db, req.arkhamdb_id))
