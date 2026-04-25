"""卡牌 API：初始化编排、浏览、详情、筛选"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.config import settings
from app.models.card import CardIndex, LocalCardFile, TTSCardImage, SharedCardBack, MappingStatus
from app.models.errata import Errata
from app.schemas.card import CardIndexResponse, CardDetailResponse, LocalCardFileResponse, TTSCardImageResponse
from app.services.scanner import scan_card_database, detect_double_sided, load_card_content
from app.services.tts_parser import scan_tts_directory, find_shared_backs

router = APIRouter(prefix="/api/cards", tags=["卡牌"])


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
    double_sided_ids = detect_double_sided(local_cards)

    for sc in local_cards:
        existing = await db.get(CardIndex, sc.arkhamdb_id)
        if not existing:
            existing = CardIndex(arkhamdb_id=sc.arkhamdb_id)
        existing.name_zh = sc.name_zh
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

    # Step 2: 扫描 TTS 英文
    en_root = project_root / settings.sced_downloads / "campaign"
    if en_root.exists():
        en_cards = scan_tts_directory(en_root, "英文")
        for ec in en_cards:
            # 为 TTS 卡牌确保 card_index 占位条目存在
            await _ensure_card_index(db, ec.arkhamdb_id)

            tts = await db.execute(
                select(TTSCardImage).where(
                    TTSCardImage.arkhamdb_id == ec.arkhamdb_id,
                    TTSCardImage.source == "英文"
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
        project_root / settings.sced_downloads / "language-pack" / "Simplified Chinese - Campaigns",
        project_root / settings.sced_downloads / "language-pack" / "Simplified Chinese - Player Cards",
    ]
    for zh_root in zh_roots:
        if zh_root.exists():
            zh_cards = scan_tts_directory(zh_root, "中文")
            for zc in zh_cards:
                # 为 TTS 卡牌确保 card_index 占位条目存在
                await _ensure_card_index(db, zc.arkhamdb_id)

                tts = await db.execute(
                    select(TTSCardImage).where(
                        TTSCardImage.arkhamdb_id == zc.arkhamdb_id,
                        TTSCardImage.source == "中文"
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
    tts_en = en_result.scalar_one_or_none()

    zh_result = await db.execute(
        select(TTSCardImage).where(
            TTSCardImage.arkhamdb_id == arkhamdb_id,
            TTSCardImage.source == "中文"
        )
    )
    tts_zh = zh_result.scalar_one_or_none()

    return CardDetailResponse(
        index=CardIndexResponse.model_validate(index),
        local_files=[LocalCardFileResponse.model_validate(f) for f in local_files],
        tts_en=TTSCardImageResponse.model_validate(tts_en) if tts_en else None,
        tts_zh=TTSCardImageResponse.model_validate(tts_zh) if tts_zh else None,
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


@router.post("/preview")
async def preview_card(body: dict, db: AsyncSession = Depends(get_db)):
    """预览渲染卡牌"""
    from app.services.renderer import render_card_preview

    preview_dir = settings.project_root / settings.cache_dir / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)

    arkhamdb_id = body.get("arkhamdb_id", "preview")
    card_content = body.get("content", {})

    result_path = render_card_preview(card_content, preview_dir, arkhamdb_id)
    if result_path is None:
        raise HTTPException(status_code=500, detail="渲染失败")

    return {"preview_path": result_path}


@router.post("/rescan")
async def rescan(db: AsyncSession = Depends(get_db)):
    """重新执行全量扫描"""
    await run_full_initialization(db)
    return {"status": "ok", "message": "重新扫描完成"}
