"""TTS 卡图到本地 .card 文件面的映射索引。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select, or_, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.card import CardIndex, LocalCardFile, TTSCardImage

SOURCES = {"英文", "中文"}
SIDES = {"front", "back"}
BACK_PRESETS: dict[str, dict[str, str]] = {
    "player_card_back": {
        "key": "player_card_back",
        "label": "玩家卡背",
        "back_url": "https://steamusercontent-a.akamaihd.net/ugc/2342503777940352139/A2D42E7E5C43D045D72CE5CFC907E4F886C8C690/",
        "description": "玩家卡通用共享卡背",
    },
    "encounter_card_back": {
        "key": "encounter_card_back",
        "label": "遭遇卡背",
        "back_url": "https://steamusercontent-a.akamaihd.net/ugc/2342503777940351785/F64D8EFB75A9E15446D24343DA0A6EEF5B3E43DB/",
        "description": "遭遇卡通用共享卡背",
    },
}



def tts_candidate_priority(tts: TTSCardImage) -> tuple[int, int, int, str]:
    """同一 arkhamdb_id 存在多个 TTS 对象时的默认候选优先级。"""
    path = tts.relative_json_path or ""
    is_nested_state = "/" in path
    is_promo = "promo" in path.lower() or "parallel" in path.lower()
    return (1 if is_nested_state else 0, 1 if is_promo else 0, tts.id or 0, path)

def get_mapping_index_path() -> Path:
    """返回由卡牌数据库仓库版本管理的映射索引路径。"""
    path = (settings.project_root / settings.local_card_db / "mapping_index.json").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _index_path() -> Path:
    return get_mapping_index_path()


def _empty_index() -> dict[str, Any]:
    return {"version": 1, "cards": {}}


def load_mapping_index() -> dict[str, Any]:
    path = _index_path()
    if not path.exists():
        return _empty_index()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _empty_index()
    if not isinstance(data, dict):
        return _empty_index()
    data.setdefault("version", 1)
    data.setdefault("cards", {})
    return data


def save_mapping_index(data: dict[str, Any]) -> None:
    path = _index_path()
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def get_card_back_presets() -> list[dict[str, str]]:
    """返回可用于单面卡发布的卡背预设。"""
    return list(BACK_PRESETS.values())


def _preset_by_key(preset_key: str) -> dict[str, str]:
    preset = BACK_PRESETS.get(preset_key)
    if not preset:
        raise ValueError("未知的卡背预设")
    return preset


def _face_back_overrides(record: dict[str, Any], local_faces: list[str]) -> dict[str, Any]:
    faces = record.get("faces", {}) if isinstance(record, dict) else {}
    return {
        face: faces.get(face, {}).get("back_override")
        for face in local_faces
        if isinstance(faces.get(face, {}), dict)
    }


def _card_record(index: dict[str, Any], arkhamdb_id: str) -> dict[str, Any]:
    cards = index.setdefault("cards", {})
    record = cards.setdefault(arkhamdb_id, {"faces": {}, "confirmed": False})
    record.setdefault("faces", {})
    record.setdefault("confirmed", False)
    return record


def bind_mapping(
    arkhamdb_id: str,
    local_face: str,
    source: str,
    tts_id: int,
    tts_side: str,
    username: str,
) -> dict[str, Any]:
    if source not in SOURCES:
        raise ValueError("数据源必须是英文或中文")
    if tts_side not in SIDES:
        raise ValueError("TTS 面必须是 front 或 back")

    index = load_mapping_index()
    record = _card_record(index, arkhamdb_id)
    face_record = record["faces"].setdefault(local_face, {})
    face_record[source] = {
        "tts_id": tts_id,
        "tts_side": tts_side,
        "updated_by": username,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    record["confirmed"] = False
    save_mapping_index(index)
    return record


def unbind_mapping(arkhamdb_id: str, local_face: str, source: str) -> dict[str, Any]:
    index = load_mapping_index()
    record = _card_record(index, arkhamdb_id)
    face_record = record["faces"].setdefault(local_face, {})
    face_record.pop(source, None)
    record["confirmed"] = False
    save_mapping_index(index)
    return record


def swap_source_faces(arkhamdb_id: str, source: str) -> dict[str, Any]:
    if source not in SOURCES:
        raise ValueError("数据源必须是英文或中文")
    index = load_mapping_index()
    record = _card_record(index, arkhamdb_id)
    faces = record["faces"]
    a_value = faces.setdefault("a", {}).get(source)
    b_value = faces.setdefault("b", {}).get(source)
    if a_value is None and b_value is None:
        return record
    if b_value is None:
        faces["b"][source] = a_value
        faces["a"].pop(source, None)
    elif a_value is None:
        faces["a"][source] = b_value
        faces["b"].pop(source, None)
    else:
        faces["a"][source], faces["b"][source] = b_value, a_value
    record["confirmed"] = False
    save_mapping_index(index)
    return record


def set_back_override(
    arkhamdb_id: str,
    local_face: str,
    preset_key: str,
    username: str,
    is_single_sided: bool,
) -> dict[str, Any]:
    """为单面卡的本地预发布背面设置共享卡背。"""
    if not is_single_sided:
        raise ValueError("只有单面卡需要设置卡背预设")
    preset = _preset_by_key(preset_key)
    index = load_mapping_index()
    record = _card_record(index, arkhamdb_id)
    face_record = record["faces"].setdefault(local_face, {})
    face_record["back_override"] = {
        "preset_key": preset["key"],
        "label": preset["label"],
        "back_url": preset["back_url"],
        "source": "本地预发布",
        "reason": "用户选择单面卡发布卡背",
        "updated_by": username,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    record["confirmed"] = False
    save_mapping_index(index)
    return record


def clear_back_override(arkhamdb_id: str, local_face: str, is_single_sided: bool) -> dict[str, Any]:
    """清除单面卡的本地预发布卡背设置。"""
    if not is_single_sided:
        raise ValueError("双面卡不需要设置卡背预设")
    index = load_mapping_index()
    record = _card_record(index, arkhamdb_id)
    face_record = record["faces"].setdefault(local_face, {})
    face_record.pop("back_override", None)
    record["confirmed"] = False
    save_mapping_index(index)
    return record


def confirm_card_mapping(arkhamdb_id: str, username: str) -> dict[str, Any]:
    index = load_mapping_index()
    record = _card_record(index, arkhamdb_id)
    record["confirmed"] = True
    record["confirmed_by"] = username
    record["confirmed_at"] = datetime.now(timezone.utc).isoformat()
    save_mapping_index(index)
    return record


async def resolve_card_image_mappings(db: AsyncSession, arkhamdb_id: str) -> list[dict[str, Any]]:
    local_files = (
        await db.execute(
            select(LocalCardFile)
            .where(LocalCardFile.arkhamdb_id == arkhamdb_id)
            .order_by(LocalCardFile.face)
        )
    ).scalars().all()

    index = load_mapping_index()
    record = index.get("cards", {}).get(arkhamdb_id, {})
    face_records = record.get("faces", {}) if isinstance(record, dict) else {}
    explicit_tts_ids = {
        mapping.get("tts_id")
        for source_map in face_records.values()
        for mapping in source_map.values()
        if isinstance(mapping, dict) and mapping.get("tts_id")
    }
    explicit_lookup_ids = {
        mapping.get("tts_lookup_id")
        for source_map in face_records.values()
        for mapping in source_map.values()
        if isinstance(mapping, dict) and mapping.get("tts_lookup_id")
    }
    base_id = arkhamdb_id[:-1] if arkhamdb_id[-1:].isalpha() else arkhamdb_id
    candidate_ids = {arkhamdb_id, base_id, *explicit_lookup_ids}
    tts_items = (
        await db.execute(
            select(TTSCardImage).where(
                or_(TTSCardImage.arkhamdb_id.in_(candidate_ids), TTSCardImage.id.in_(explicit_tts_ids or {-1}))
            )
        )
    ).scalars().all()
    tts_by_id = {item.id: item for item in tts_items}
    sorted_tts_items = sorted(tts_items, key=tts_candidate_priority)
    first_by_source: dict[str, TTSCardImage] = {}
    for item in sorted_tts_items:
        if item.arkhamdb_id == arkhamdb_id:
            first_by_source.setdefault(item.source, item)
    for item in sorted_tts_items:
        if item.arkhamdb_id in explicit_lookup_ids:
            first_by_source.setdefault(item.source, item)
    for item in sorted_tts_items:
        first_by_source.setdefault(item.source, item)

    def resolve_tts(source: str, explicit: dict[str, Any]) -> tuple[TTSCardImage | None, bool]:
        """优先用稳定 arkhamdb 编号解析，避免跨环境数据库自增 ID 漂移。"""
        lookup_id = explicit.get("tts_lookup_id")
        if lookup_id:
            for item in sorted_tts_items:
                if item.source == source and item.arkhamdb_id == lookup_id:
                    return item, True
        tts_id = explicit.get("tts_id")
        if tts_id:
            tts = tts_by_id.get(tts_id)
            if tts and tts.source == source:
                return tts, True
        return first_by_source.get(source), False

    resolved: list[dict[str, Any]] = []

    for local_file in local_files:
        fallback_side = "back" if local_file.face == "b" else "front"
        english_explicit = face_records.get(local_file.face, {}).get("英文", {})
        canonical_side = english_explicit.get("tts_side") or fallback_side
        for source in ["英文", "中文"]:
            explicit = face_records.get(local_file.face, {}).get(source, {})
            tts_side = explicit.get("tts_side") or canonical_side
            tts, is_explicit = resolve_tts(source, explicit)
            resolved.append({
                "local_face": local_file.face,
                "source": source,
                "tts_id": tts.id if tts else None,
                "tts_side": tts_side,
                "image_url": f"/api/cards/tts-images/{tts.id}/{tts_side}" if tts else None,
                "status": "已绑定" if is_explicit else ("自动候选" if tts else "未找到"),
                "relative_json_path": tts.relative_json_path if tts else None,
                "card_id": tts.card_id if tts else None,
            })
    return resolved


async def get_mapping_detail(db: AsyncSession, arkhamdb_id: str) -> dict[str, Any]:
    card = await db.get(CardIndex, arkhamdb_id)
    local_files = (
        await db.execute(
            select(LocalCardFile)
            .where(LocalCardFile.arkhamdb_id == arkhamdb_id)
            .order_by(LocalCardFile.face)
        )
    ).scalars().all()
    index = load_mapping_index()
    record = index.get("cards", {}).get(arkhamdb_id, {})
    local_faces = [item.face for item in local_files]
    return {
        "arkhamdb_id": arkhamdb_id,
        "card": card,
        "local_files": local_files,
        "is_single_sided": len(local_files) == 1,
        "back_overrides": _face_back_overrides(record, local_faces),
        "confirmed": bool(record.get("confirmed")) if isinstance(record, dict) else False,
        "confirmed_by": record.get("confirmed_by") if isinstance(record, dict) else None,
        "confirmed_at": record.get("confirmed_at") if isinstance(record, dict) else None,
        "image_mappings": await resolve_card_image_mappings(db, arkhamdb_id),
        "index_path": str(_index_path()),
    }


async def search_tts_candidates(
    db: AsyncSession,
    source: str | None,
    keyword: str | None,
    limit: int = 50,
) -> list[TTSCardImage]:
    query = select(TTSCardImage).outerjoin(CardIndex, CardIndex.arkhamdb_id == TTSCardImage.arkhamdb_id)
    if source:
        query = query.where(TTSCardImage.source == source)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        query = query.where(or_(
            TTSCardImage.arkhamdb_id.ilike(pattern),
            TTSCardImage.relative_json_path.ilike(pattern),
            cast(TTSCardImage.card_id, String).ilike(pattern),
            CardIndex.name_zh.ilike(pattern),
            CardIndex.name_en.ilike(pattern),
        ))
    query = query.order_by(TTSCardImage.source, TTSCardImage.arkhamdb_id, TTSCardImage.relative_json_path).limit(min(limit, 200))
    return list((await db.execute(query)).scalars().all())
