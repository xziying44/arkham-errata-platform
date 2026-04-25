"""勘误 API：提交、查询、预览"""

import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.errata import Errata, ErrataStatus
from app.models.user import User, UserRole
from app.schemas.errata import ErrataSubmitRequest, ErrataResponse, ErrataDetailResponse
from app.api.auth import require_user
from app.services.renderer import render_card_preview
from app.config import settings

router = APIRouter(prefix="/api/errata", tags=["勘误"])


@router.post("", response_model=ErrataResponse)
async def submit_errata(
    body: ErrataSubmitRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """提交一条新的勘误记录"""
    errata = Errata(
        arkhamdb_id=body.arkhamdb_id,
        user_id=current_user.id,
        original_content=json.dumps(body.original_content, ensure_ascii=False),
        modified_content=json.dumps(body.modified_content, ensure_ascii=False),
        status=ErrataStatus.PENDING,
    )
    db.add(errata)
    await db.commit()
    await db.refresh(errata)
    return errata


@router.get("")
async def list_my_errata(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """查询当前用户的勘误记录列表，支持按状态筛选和分页"""
    query = select(Errata).where(Errata.user_id == current_user.id)
    if status:
        query = query.where(Errata.status == status)
    query = query.order_by(Errata.created_at.desc())

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()
    query = query.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(query)).scalars().all()

    return {
        "items": [ErrataResponse.model_validate(e) for e in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{errata_id}", response_model=ErrataDetailResponse)
async def get_errata_detail(
    errata_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """获取单条勘误记录的完整详情"""
    errata = await db.get(Errata, errata_id)
    if not errata:
        raise HTTPException(status_code=404, detail="勘误记录不存在")
    if current_user.role != UserRole.ADMIN and errata.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权查看")

    return ErrataDetailResponse(
        id=errata.id,
        arkhamdb_id=errata.arkhamdb_id,
        user_id=errata.user_id,
        status=errata.status.value,
        review_note=errata.review_note,
        batch_id=errata.batch_id,
        created_at=errata.created_at,
        updated_at=errata.updated_at,
        original_content=json.loads(errata.original_content),
        modified_content=json.loads(errata.modified_content),
        rendered_preview=errata.rendered_preview,
    )


@router.post("/{errata_id}/preview")
async def generate_errata_preview(
    errata_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """为指定勘误记录的修改内容生成渲染预览图"""
    errata = await db.get(Errata, errata_id)
    if not errata:
        raise HTTPException(status_code=404, detail="勘误记录不存在")

    preview_dir = settings.project_root / settings.cache_dir / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)

    modified = json.loads(errata.modified_content)
    path = render_card_preview(modified, preview_dir, f"errata_{errata_id}")
    if path:
        errata.rendered_preview = path
        await db.commit()
    return {"preview_path": path}
