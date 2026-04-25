"""审核 API - 管理员审核勘误记录"""

import json
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from app.database import get_db
from app.models.errata import Errata, ErrataStatus
from app.models.user import User
from app.schemas.errata import ErrataResponse
from app.api.auth import require_admin

router = APIRouter(prefix="/api/admin/review", tags=["审核"])


@router.get("/pending")
async def list_pending_errata(
    batch_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """获取待审核勘误列表，按 arkhamdb_id 去重（仅展示最新一条）"""
    query = select(Errata).where(Errata.status == ErrataStatus.PENDING)
    if batch_id:
        query = query.where(Errata.batch_id == batch_id)
    query = query.order_by(Errata.arkhamdb_id, Errata.created_at.desc())

    result = await db.execute(query)
    items = result.scalars().all()

    # 按 arkhamdb_id 去重，保留最新提交
    latest: dict[str, Errata] = {}
    for e in items:
        if e.arkhamdb_id not in latest:
            latest[e.arkhamdb_id] = e

    return {
        "items": [ErrataResponse.model_validate(e) for e in latest.values()],
        "total": len(latest),
    }


@router.get("/batches")
async def list_batches(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """获取所有审核批次列表"""
    result = await db.execute(
        select(
            Errata.batch_id,
            func.count(),
            func.min(Errata.created_at),
        )
        .where(Errata.batch_id.isnot(None))
        .group_by(Errata.batch_id)
        .order_by(func.min(Errata.created_at).desc())
    )
    return [
        {
            "batch_id": row[0],
            "count": row[1],
            "created_at": str(row[2]),
        }
        for row in result
    ]


@router.post("/approve")
async def batch_approve(
    body: dict,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """批量批准勘误记录"""
    batch_id = body.get("batch_id") or str(uuid.uuid4())[:8]
    ids = body.get("ids", [])

    if not ids:
        raise HTTPException(status_code=400, detail="请选择要审核的勘误")

    await db.execute(
        update(Errata)
        .where(Errata.id.in_(ids))
        .values(
            status=ErrataStatus.APPROVED,
            reviewer_id=admin.id,
            batch_id=batch_id,
        )
    )
    await db.commit()

    return {"approved": len(ids), "batch_id": batch_id}


@router.post("/reject")
async def batch_reject(
    body: dict,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """批量驳回勘误记录"""
    ids = body.get("ids", [])
    note = body.get("note", "")

    if not ids:
        raise HTTPException(status_code=400, detail="请选择要驳回的勘误")

    await db.execute(
        update(Errata)
        .where(Errata.id.in_(ids))
        .values(
            status=ErrataStatus.REJECTED,
            reviewer_id=admin.id,
            review_note=note,
        )
    )
    await db.commit()

    return {"rejected": len(ids)}


@router.get("/approved-by-batch/{batch_id}")
async def get_approved_by_batch(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """获取指定批次中已批准的勘误详情"""
    result = await db.execute(
        select(Errata).where(
            Errata.batch_id == batch_id,
            Errata.status == ErrataStatus.APPROVED,
        )
    )
    items = result.scalars().all()

    return {
        "batch_id": batch_id,
        "items": [
            {
                "id": e.id,
                "arkhamdb_id": e.arkhamdb_id,
                "modified_content": json.loads(e.modified_content),
                "original_content": json.loads(e.original_content),
            }
            for e in items
        ],
        "total": len(items),
    }
