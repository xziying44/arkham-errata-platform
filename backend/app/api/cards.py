"""卡牌 API：初始化编排、浏览、详情、筛选"""
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from app.database import get_db
from app.config import settings
from app.models.card import CardIndex, LocalCardFile, TTSCardImage, SharedCardBack, MappingStatus
from app.models.errata import Errata, ErrataStatus
from app.models.errata_draft import ErrataAuditLog, ErrataDraft, ErrataDraftStatus
from app.models.user import User
from app.utils.security import decode_token
from app.schemas.card import CardIndexResponse, CardDetailResponse, LocalCardFileResponse, TTSCardImageResponse
from app.services.scanner import scan_card_database, detect_double_sided, load_card_content
from app.services.tts_parser import scan_tts_directory, find_shared_backs
from app.services.mapping_index import get_mapping_detail, resolve_card_image_mappings
from app.services.image_cache import download_and_cut_sheet, ensure_preview_cached_image
from app.services.local_card_index import build_local_card_index, ensure_local_card_index, get_local_card_face_index, search_local_card_index
from app.services.tts_cache_warmer import get_cache_warm_status, start_tts_cache_warmer

router = APIRouter(prefix="/api/cards", tags=["卡牌"])
optional_security_scheme = HTTPBearer(auto_error=False)


async def optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    payload = decode_token(credentials.credentials)
    if payload is None:
        return None
    result = await db.execute(select(User).where(User.id == payload["user_id"]))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        return None
    return user


def _preview_url_from_path(result_path: str) -> str:
    """将预览图片本机路径转换为浏览器可访问 URL"""
    try:
        return f"/static/cache/{Path(result_path).relative_to(settings.project_root / settings.cache_dir)}"
    except ValueError:
        return result_path


def _draft_content_matches_keyword(draft: ErrataDraft, keyword: str) -> bool:
    """判断活跃勘误副本内容是否命中搜索词。"""
    if not keyword:
        return False
    text = f"{draft.arkhamdb_id} {json.dumps(draft.modified_faces or {}, ensure_ascii=False, sort_keys=True)}"
    return keyword in text.lower()


def _overlay_draft_face_titles(item: dict, draft: ErrataDraft) -> None:
    """用活跃勘误副本覆盖树节点的正背面标题。"""
    for face, content in (draft.modified_faces or {}).items():
        if not isinstance(content, dict):
            continue
        title = content.get("name")
        subtitle = content.get("subtitle")
        if isinstance(title, str) and title:
            item["face_titles"][face] = title
        if isinstance(subtitle, str) and subtitle:
            item["face_subtitles"][face] = subtitle


def _render_local_face_preview(arkhamdb_id: str, file_record: LocalCardFile) -> dict:
    """渲染单个本地 .card 面，便于前端渐进式展示"""
    from app.services.renderer import render_card_preview

    preview_dir = settings.project_root / settings.cache_dir / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    content = load_card_content(
        settings.project_root / settings.local_card_db,
        file_record.relative_path,
        include_picture=True,
    )
    if not content:
        return {
            "face": file_record.face,
            "relative_path": file_record.relative_path,
            "preview_url": None,
            "error": "无法读取文件内容",
        }
    result_path = render_card_preview(
        content,
        preview_dir,
        f"{arkhamdb_id}_{file_record.face}",
        dpi=settings.preview_render_dpi,
        quality=settings.preview_jpeg_quality,
    )
    return {
        "face": file_record.face,
        "relative_path": file_record.relative_path,
        "preview_url": _preview_url_from_path(result_path) if result_path else None,
        "error": None if result_path else "渲染失败",
    }


async def _merge_original_picture(
    db: AsyncSession,
    arkhamdb_id: str,
    face: str,
    content: dict,
) -> dict:
    """手动预览时从原始 .card 补回 picture_base64"""
    if content.get("picture_base64"):
        return content
    result = await db.execute(
        select(LocalCardFile).where(
            LocalCardFile.arkhamdb_id == arkhamdb_id,
            LocalCardFile.face == face,
        )
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        return content
    original = load_card_content(
        settings.project_root / settings.local_card_db,
        file_record.relative_path,
        include_picture=True,
    )
    if original and original.get("picture_base64"):
        return {**content, "picture_base64": original["picture_base64"]}
    return content


async def _ensure_card_index(db: AsyncSession, arkhamdb_id: str) -> CardIndex:
    """确保 card_index 中存在对应的条目，不存在则创建占位记录"""
    existing = await db.get(CardIndex, arkhamdb_id)
    if not existing:
        existing = CardIndex(arkhamdb_id=arkhamdb_id)
        db.add(existing)
        # 立即 flush 以便后续 TTS 外键引用该条目
        await db.flush()
    return existing


async def run_full_initialization(db: AsyncSession):
    """首次初始化：扫描全部数据源 + 建立索引 + 标记映射状态"""
    project_root = settings.project_root

    # Step 1: 扫描本地 .card 文件
    local_cards = scan_card_database(project_root / settings.local_card_db)
    build_local_card_index(project_root / settings.local_card_db)
    double_sided_ids = detect_double_sided(local_cards)
    front_name_by_id: dict[str, str] = {}
    for sc in local_cards:
        if sc.face == "a" or sc.arkhamdb_id not in front_name_by_id:
            front_name_by_id[sc.arkhamdb_id] = sc.name_zh

    for sc in local_cards:
        existing = await db.get(CardIndex, sc.arkhamdb_id)
        if not existing:
            existing = CardIndex(arkhamdb_id=sc.arkhamdb_id)
        existing.name_zh = front_name_by_id.get(sc.arkhamdb_id, sc.name_zh)
        existing.category = sc.category
        existing.cycle = sc.cycle
        existing.is_double_sided = sc.arkhamdb_id in double_sided_ids
        db.add(existing)

        # Upsert LocalCardFile
        file_result = await db.execute(
            select(LocalCardFile).where(LocalCardFile.relative_path == sc.relative_path)
        )
        file_record = file_result.scalar_one_or_none()
        if not file_record:
            file_record = LocalCardFile(relative_path=sc.relative_path)
        file_record.arkhamdb_id = sc.arkhamdb_id
        file_record.face = sc.face
        file_record.content_hash = sc.content_hash
        file_record.last_modified = sc.last_modified
        db.add(file_record)

    # 先 flush 本地数据，确保后续 TTS 外键不会冲突
    await db.flush()

    # Step 2: 扫描 TTS 英文。SCED-downloads 只包含剧本英文图，SCED 仓库补充官方英文玩家卡。
    en_roots = [
        project_root / settings.sced_downloads / "decomposed" / "campaign",
        project_root / settings.sced_repo / "objects" / "AllPlayerCards.15bb07",
    ]
    for en_root in en_roots:
        if not en_root.exists():
            continue
        en_cards = scan_tts_directory(en_root, "英文")
        for ec in en_cards:
            # 为 TTS 卡牌确保 card_index 占位条目存在
            await _ensure_card_index(db, ec.arkhamdb_id)

            tts = await db.execute(
                select(TTSCardImage).where(
                    TTSCardImage.source == "英文",
                    TTSCardImage.relative_json_path == ec.relative_json_path,
                )
            )
            existing_tts = tts.scalar_one_or_none()
            if not existing_tts:
                existing_tts = TTSCardImage(arkhamdb_id=ec.arkhamdb_id, source="英文")
            existing_tts.relative_json_path = ec.relative_json_path
            existing_tts.card_id = ec.card_id
            existing_tts.deck_key = ec.deck_key
            existing_tts.face_url = ec.face_url
            existing_tts.back_url = ec.back_url
            existing_tts.grid_width = ec.grid_width
            existing_tts.grid_height = ec.grid_height
            existing_tts.grid_position = ec.grid_position
            existing_tts.unique_back = ec.unique_back
            db.add(existing_tts)

        # 提取共享卡背
        shared_backs = find_shared_backs(en_cards, "英文")
        for sb in shared_backs:
            existing = await db.execute(
                select(SharedCardBack).where(SharedCardBack.back_url == sb["back_url"])
            )
            if not existing.scalar_one_or_none():
                db.add(SharedCardBack(
                    back_url=sb["back_url"],
                    source=sb["source"],
                    name=sb.get("deck_key", ""),
                    type="调查员" if sb.get("deck_key", "") else "",
                ))

    # Step 3: 扫描 TTS 中文
    zh_roots = [
        project_root / settings.sced_downloads / "decomposed" / "language-pack" / "Simplified Chinese - Campaigns",
        project_root / settings.sced_downloads / "decomposed" / "language-pack" / "Simplified Chinese - Player Cards",
    ]
    for zh_root in zh_roots:
        if zh_root.exists():
            zh_cards = scan_tts_directory(zh_root, "中文")
            for zc in zh_cards:
                # 为 TTS 卡牌确保 card_index 占位条目存在
                await _ensure_card_index(db, zc.arkhamdb_id)

                tts = await db.execute(
                    select(TTSCardImage).where(
                        TTSCardImage.source == "中文",
                        TTSCardImage.relative_json_path == zc.relative_json_path,
                    )
                )
                existing_tts = tts.scalar_one_or_none()
                if not existing_tts:
                    existing_tts = TTSCardImage(arkhamdb_id=zc.arkhamdb_id, source="中文")
                existing_tts.relative_json_path = zc.relative_json_path
                existing_tts.card_id = zc.card_id
                existing_tts.deck_key = zc.deck_key
                existing_tts.face_url = zc.face_url
                existing_tts.back_url = zc.back_url
                existing_tts.grid_width = zc.grid_width
                existing_tts.grid_height = zc.grid_height
                existing_tts.grid_position = zc.grid_position
                existing_tts.unique_back = zc.unique_back
                db.add(existing_tts)

    # Step 4: 标记映射状态
    result = await db.execute(select(CardIndex))
    all_cards = result.scalars().all()
    for card in all_cards:
        en_exists = await db.scalar(
            select(TTSCardImage).where(
                TTSCardImage.arkhamdb_id == card.arkhamdb_id,
                TTSCardImage.source == "英文"
            ).limit(1)
        )
        zh_exists = await db.scalar(
            select(TTSCardImage).where(
                TTSCardImage.arkhamdb_id == card.arkhamdb_id,
                TTSCardImage.source == "中文"
            ).limit(1)
        )
        if en_exists and zh_exists:
            card.mapping_status = MappingStatus.CONFIRMED
        elif en_exists or zh_exists:
            card.mapping_status = MappingStatus.PENDING
        else:
            card.mapping_status = MappingStatus.PENDING
        db.add(card)

    await db.commit()


@router.post("/initialize")
async def initialize(db: AsyncSession = Depends(get_db)):
    """触发首次全量初始化扫描"""
    await run_full_initialization(db)
    return {"status": "ok", "message": "初始化完成"}


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """获取数据库统计信息"""
    cards_count = (await db.execute(select(func.count()).select_from(CardIndex))).scalar()
    errata_count = (await db.execute(select(func.count()).select_from(Errata))).scalar()
    en_count = (await db.execute(
        select(func.count()).select_from(TTSCardImage).where(TTSCardImage.source == "英文")
    )).scalar()
    zh_count = (await db.execute(
        select(func.count()).select_from(TTSCardImage).where(TTSCardImage.source == "中文")
    )).scalar()
    return {
        "total_cards": cards_count,
        "total_errata": errata_count,
        "english_tts_cards": en_count,
        "chinese_tts_cards": zh_count,
    }


@router.get("")
async def list_cards(
    category: str | None = None,
    cycle: str | None = None,
    mapping_status: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """浏览卡牌列表，支持筛选和分页"""
    query = select(CardIndex)
    if category:
        query = query.where(CardIndex.category == category)
    if cycle:
        query = query.where(CardIndex.cycle == cycle)
    if mapping_status:
        query = query.where(CardIndex.mapping_status == mapping_status)
    if keyword:
        query = query.where(
            CardIndex.name_zh.ilike(f"%{keyword}%")
            | CardIndex.name_en.ilike(f"%{keyword}%")
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    query = query.offset((page - 1) * page_size).limit(page_size)
    cards = (await db.execute(query)).scalars().all()

    return {
        "items": [CardIndexResponse.model_validate(c) for c in cards],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/filters")
async def get_filter_options(db: AsyncSession = Depends(get_db)):
    """获取可用的筛选选项（分类、循环）"""
    cat_result = await db.execute(select(CardIndex.category.distinct()))
    cyc_result = await db.execute(select(CardIndex.cycle.distinct()))
    return {
        "categories": sorted([c[0] for c in cat_result if c[0]]),
        "cycles": sorted([c[0] for c in cyc_result if c[0]]),
    }


@router.get("/tree")
async def get_local_card_tree(
    keyword: str | None = None,
    scope: str = "all",
    package_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(optional_current_user),
):
    """按卡牌数据库目录组织卡牌树，仅包含存在本地 .card 文件的卡牌。"""
    local_card_root = settings.project_root / settings.local_card_db
    ensure_local_card_index(local_card_root)
    base_query = (
        select(CardIndex, LocalCardFile)
        .join(LocalCardFile, LocalCardFile.arkhamdb_id == CardIndex.arkhamdb_id)
    )
    normalized_keyword = keyword.strip().lower() if keyword else ""
    order_columns = (CardIndex.category, CardIndex.cycle, CardIndex.arkhamdb_id, LocalCardFile.face)

    if normalized_keyword:
        pattern = f"%{keyword.strip()}%"
        db_query = base_query.where(
            or_(
                CardIndex.arkhamdb_id.ilike(pattern),
                CardIndex.name_zh.ilike(pattern),
                CardIndex.name_en.ilike(pattern),
                LocalCardFile.relative_path.ilike(pattern),
            )
        )
        rows = list((await db.execute(db_query.order_by(*order_columns))).all())
        seen = {(card.arkhamdb_id, file_record.relative_path) for card, file_record in rows}

        matched_paths = search_local_card_index(local_card_root, normalized_keyword)
        encounter_rows = (await db.execute(base_query.order_by(*order_columns))).all()
        for card, file_record in encounter_rows:
            row_key = (card.arkhamdb_id, file_record.relative_path)
            if row_key in seen:
                continue
            if file_record.relative_path in matched_paths:
                rows.append((card, file_record))
                seen.add(row_key)

        active_draft_result = await db.execute(
            select(ErrataDraft)
            .where(ErrataDraft.archived_at.is_(None))
            .order_by(ErrataDraft.updated_at.desc(), ErrataDraft.id.desc())
        )
        matched_draft_ids = {
            draft.arkhamdb_id
            for draft in active_draft_result.scalars().all()
            if _draft_content_matches_keyword(draft, normalized_keyword)
        }
        if matched_draft_ids:
            draft_rows = (
                await db.execute(
                    base_query
                    .where(CardIndex.arkhamdb_id.in_(matched_draft_ids))
                    .order_by(*order_columns)
                )
            ).all()
            for card, file_record in draft_rows:
                row_key = (card.arkhamdb_id, file_record.relative_path)
                if row_key not in seen:
                    rows.append((card, file_record))
                    seen.add(row_key)
    else:
        rows = list((await db.execute(base_query.order_by(*order_columns))).all())

    grouped: dict[str, dict] = {}
    for card, file_record in rows:
        item = grouped.setdefault(card.arkhamdb_id, {
            "arkhamdb_id": card.arkhamdb_id,
            "name_zh": card.name_zh,
            "name_en": card.name_en,
            "category": card.category,
            "cycle": card.cycle,
            "expansion": card.expansion,
            "mapping_status": card.mapping_status.value,
            "is_double_sided": card.is_double_sided,
            "pending_errata_count": 0,
            "approved_errata_count": 0,
            "latest_batch_id": None,
            "errata_state": "正常",
            "participant_usernames": [],
            "package_id": None,
            "latest_audit_at": None,
            "face_titles": {},
            "face_subtitles": {},
            "local_files": [],
        })
        face_index = get_local_card_face_index(local_card_root, file_record.relative_path)
        face_title = face_index.title if face_index else ""
        face_subtitle = face_index.subtitle if face_index else ""
        if face_title:
            item["face_titles"][file_record.face] = face_title
        if face_subtitle:
            item["face_subtitles"][file_record.face] = face_subtitle
        item["local_files"].append(LocalCardFileResponse.model_validate(file_record).model_dump())

    if grouped:
        draft_result = await db.execute(
            select(ErrataDraft)
            .where(ErrataDraft.arkhamdb_id.in_(grouped.keys()))
            .where(ErrataDraft.archived_at.is_(None))
        )
        drafts = {draft.arkhamdb_id: draft for draft in draft_result.scalars().all()}

        active_draft_ids = [draft.id for draft in drafts.values()]
        participants: dict[str, list[str]] = {}
        latest_audit: dict[str, str] = {}
        if active_draft_ids:
            audit_result = await db.execute(
                select(ErrataAuditLog.arkhamdb_id, User.username, func.max(ErrataAuditLog.created_at))
                .join(User, User.id == ErrataAuditLog.user_id)
                .where(ErrataAuditLog.draft_id.in_(active_draft_ids))
                .group_by(ErrataAuditLog.arkhamdb_id, User.username)
            )
            for arkhamdb_id, username, created_at in audit_result:
                participants.setdefault(arkhamdb_id, []).append(username)
                current_latest = latest_audit.get(arkhamdb_id)
                created_at_text = created_at.isoformat() if created_at else None
                if created_at_text and (current_latest is None or created_at_text > current_latest):
                    latest_audit[arkhamdb_id] = created_at_text

        for arkhamdb_id, item in grouped.items():
            draft = drafts.get(arkhamdb_id)
            if draft:
                _overlay_draft_face_titles(item, draft)
                item["errata_state"] = "待发布" if draft.status == ErrataDraftStatus.WAITING_PUBLISH else "勘误"
                item["package_id"] = draft.package_id
                if draft.status == ErrataDraftStatus.ERRATA:
                    item["pending_errata_count"] = 1
                elif draft.status == ErrataDraftStatus.WAITING_PUBLISH:
                    item["approved_errata_count"] = 1
                    item["latest_batch_id"] = str(draft.package_id) if draft.package_id else None
            item["participant_usernames"] = sorted(participants.get(arkhamdb_id, []))
            item["latest_audit_at"] = latest_audit.get(arkhamdb_id)

    if scope == "mine":
        if current_user is None:
            grouped = {}
        else:
            mine_result = await db.execute(
                select(ErrataAuditLog.arkhamdb_id)
                .join(ErrataDraft, ErrataDraft.id == ErrataAuditLog.draft_id)
                .where(ErrataAuditLog.user_id == current_user.id)
                .where(ErrataDraft.archived_at.is_(None))
                .distinct()
            )
            mine_ids = set(mine_result.scalars().all())
            grouped = {arkhamdb_id: item for arkhamdb_id, item in grouped.items() if arkhamdb_id in mine_ids}
    elif scope == "review":
        grouped = {arkhamdb_id: item for arkhamdb_id, item in grouped.items() if item["errata_state"] == "勘误"}
    elif scope == "package":
        grouped = {
            arkhamdb_id: item
            for arkhamdb_id, item in grouped.items()
            if package_id is not None and item["package_id"] == package_id
        }
    elif scope != "all":
        raise HTTPException(status_code=400, detail="无效的卡牌列表范围")

    tree: list[dict] = []
    category_map: dict[str, dict] = {}
    cycle_map: dict[tuple[str, str], dict] = {}
    for item in grouped.values():
        category = item["category"] or "未分类"
        cycle = item["cycle"] or "未分组"
        category_node = category_map.get(category)
        if not category_node:
            category_node = {"key": f"category:{category}", "title": category, "children": []}
            category_map[category] = category_node
            tree.append(category_node)
        cycle_key = (category, cycle)
        cycle_node = cycle_map.get(cycle_key)
        if not cycle_node:
            cycle_node = {"key": f"cycle:{category}:{cycle}", "title": cycle, "children": []}
            cycle_map[cycle_key] = cycle_node
            category_node["children"].append(cycle_node)
        title = f"{item['arkhamdb_id']} {item['name_zh'] or item['name_en']}"
        cycle_node["children"].append({"key": item["arkhamdb_id"], "title": title, "card": item})

    return {"tree": tree, "total": len(grouped)}


@router.get("/cache/status")
async def get_tts_cache_status():
    """查看后台 TTS 卡图缓存预热状态。"""
    return get_cache_warm_status()


@router.post("/cache/warm")
async def start_tts_cache_warm():
    """手动启动后台 TTS 卡图缓存预热。"""
    start_tts_cache_warmer()
    return get_cache_warm_status()


@router.get("/{arkhamdb_id}", response_model=CardDetailResponse)
async def get_card_detail(arkhamdb_id: str, db: AsyncSession = Depends(get_db)):
    """获取单张卡牌完整详情"""
    index = await db.get(CardIndex, arkhamdb_id)
    if not index:
        raise HTTPException(status_code=404, detail="卡牌不存在")

    local_result = await db.execute(
        select(LocalCardFile).where(LocalCardFile.arkhamdb_id == arkhamdb_id)
    )
    local_files = local_result.scalars().all()

    en_result = await db.execute(
        select(TTSCardImage).where(
            TTSCardImage.arkhamdb_id == arkhamdb_id,
            TTSCardImage.source == "英文"
        )
    )
    tts_en = en_result.scalars().all()

    zh_result = await db.execute(
        select(TTSCardImage).where(
            TTSCardImage.arkhamdb_id == arkhamdb_id,
            TTSCardImage.source == "中文"
        )
    )
    tts_zh = zh_result.scalars().all()

    mapping_detail = await get_mapping_detail(db, arkhamdb_id)
    return CardDetailResponse(
        index=CardIndexResponse.model_validate(index),
        local_files=[LocalCardFileResponse.model_validate(f) for f in local_files],
        tts_en=[TTSCardImageResponse.model_validate(t) for t in tts_en],
        tts_zh=[TTSCardImageResponse.model_validate(t) for t in tts_zh],
        image_mappings=mapping_detail["image_mappings"],
        is_single_sided=mapping_detail["is_single_sided"],
        back_overrides=mapping_detail["back_overrides"],
    )


@router.get("/{arkhamdb_id}/files/{face}")
async def get_card_file_content(arkhamdb_id: str, face: str, db: AsyncSession = Depends(get_db)):
    """获取 .card 文件原始内容"""
    result = await db.execute(
        select(LocalCardFile).where(
            LocalCardFile.arkhamdb_id == arkhamdb_id,
            LocalCardFile.face == face
        )
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise HTTPException(status_code=404, detail="文件不存在")

    content = load_card_content(settings.project_root / settings.local_card_db, file_record.relative_path)
    if not content:
        raise HTTPException(status_code=404, detail="无法读取文件内容")

    return {
        "relative_path": file_record.relative_path,
        "face": file_record.face,
        "content": content,
        "content_hash": file_record.content_hash,
    }


@router.post("/{arkhamdb_id}/preview-all")
async def preview_all_faces(arkhamdb_id: str, db: AsyncSession = Depends(get_db)):
    """进入编辑页时预渲染本地 .card 的所有面"""
    result = await db.execute(
        select(LocalCardFile)
        .where(LocalCardFile.arkhamdb_id == arkhamdb_id)
        .order_by(LocalCardFile.face)
    )
    files = result.scalars().all()
    if not files:
        raise HTTPException(status_code=404, detail="本地卡牌文件不存在")

    return {"items": [_render_local_face_preview(arkhamdb_id, file_record) for file_record in files]}


@router.post("/{arkhamdb_id}/preview-face/{face}")
async def preview_one_face(arkhamdb_id: str, face: str, db: AsyncSession = Depends(get_db)):
    """渲染单个本地 .card 面，避免详情页等待所有图片完成"""
    result = await db.execute(
        select(LocalCardFile).where(
            LocalCardFile.arkhamdb_id == arkhamdb_id,
            LocalCardFile.face == face,
        )
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise HTTPException(status_code=404, detail="本地卡牌文件不存在")
    return _render_local_face_preview(arkhamdb_id, file_record)


@router.get("/tts-images/{tts_id}/{side}")
async def get_tts_image(tts_id: int, side: str, db: AsyncSession = Depends(get_db)):
    """按需裁切并返回 TTS 单张卡图"""
    if side not in {"front", "back"}:
        raise HTTPException(status_code=400, detail="卡图面必须是 front 或 back")

    tts = await db.get(TTSCardImage, tts_id)
    if not tts:
        raise HTTPException(status_code=404, detail="TTS 卡图不存在")

    cached_path = tts.cached_front_path if side == "front" else tts.cached_back_path
    if cached_path:
        path = settings.project_root / cached_path
        if path.exists():
            ensure_preview_cached_image(path)
            return FileResponse(path, media_type="image/jpeg")

    sheet_url = tts.face_url if side == "front" else tts.back_url
    if not sheet_url:
        raise HTTPException(status_code=404, detail="TTS 卡图 URL 不存在")
    cache_dir = settings.project_root / settings.cache_dir / "tts"
    cache_key = f"{tts.source}_{tts.id}_{side}"
    generated_path = download_and_cut_sheet(
        sheet_url=sheet_url,
        grid_position=tts.grid_position,
        grid_width=tts.grid_width,
        grid_height=tts.grid_height,
        cache_dir=cache_dir,
        cache_key=cache_key,
    )
    if not generated_path:
        raise HTTPException(status_code=502, detail="下载或裁切 TTS 卡图失败")

    relative_path = str(Path(generated_path).relative_to(settings.project_root))
    if side == "front":
        tts.cached_front_path = relative_path
    else:
        tts.cached_back_path = relative_path
    await db.commit()
    return FileResponse(generated_path, media_type="image/jpeg")


@router.post("/preview")
async def preview_card(body: dict, db: AsyncSession = Depends(get_db)):
    """预览渲染卡牌"""
    from app.services.renderer import render_card_preview

    preview_dir = settings.project_root / settings.cache_dir / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)

    arkhamdb_id = body.get("arkhamdb_id", "preview")
    card_content = body.get("content", {})
    source_id, source_face = str(arkhamdb_id), "a"
    if "_" in source_id:
        source_id, source_face = source_id.rsplit("_", 1)
    card_content = await _merge_original_picture(db, source_id, source_face, card_content)

    result_path = render_card_preview(
        card_content,
        preview_dir,
        arkhamdb_id,
        dpi=settings.preview_render_dpi,
        quality=settings.preview_jpeg_quality,
    )
    if result_path is None:
        raise HTTPException(status_code=500, detail="渲染失败")

    return {"preview_path": result_path, "preview_url": _preview_url_from_path(result_path)}


@router.post("/rescan")
async def rescan(db: AsyncSession = Depends(get_db)):
    """重新执行全量扫描"""
    await run_full_initialization(db)
    return {"status": "ok", "message": "重新扫描完成"}
