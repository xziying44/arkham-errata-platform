"""审核 API - 审核员将勘误副本生成勘误包"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_reviewer
from app.database import get_db
from app.models.errata_draft import (
    ErrataAuditAction,
    ErrataDraft,
    ErrataDraftStatus,
    ErrataPackage,
    ErrataPackageStatus,
)
from app.models.user import User
from app.services.errata_drafts import append_audit_log, get_participant_usernames

router = APIRouter(prefix="/api/admin/review", tags=["审核"])


def serialize_package(package: ErrataPackage) -> dict:
    return {
        "id": package.id,
        "package_no": package.package_no,
        "status": package.status.value,
        "note": package.note,
        "created_at": package.created_at,
        "updated_at": package.updated_at,
        "published_at": package.published_at,
    }


def make_package_no() -> str:
    return f"ERRATA-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


async def ensure_no_active_package(db: AsyncSession) -> None:
    result = await db.execute(
        select(ErrataPackage).where(
            ErrataPackage.status.in_([ErrataPackageStatus.WAITING_PUBLISH, ErrataPackageStatus.PUBLISHING])
        )
    )
    if result.scalars().first() is not None:
        raise HTTPException(status_code=409, detail="当前已有待发布或发布中的勘误包，请先发布或解锁后再生成新包")


@router.get("/pending")
async def list_pending_errata(
    db: AsyncSession = Depends(get_db),
    reviewer: User = Depends(require_reviewer),
):
    """兼容旧前端：返回当前处于“勘误”状态的副本。"""
    result = await db.execute(
        select(ErrataDraft)
        .where(ErrataDraft.status == ErrataDraftStatus.ERRATA)
        .where(ErrataDraft.archived_at.is_(None))
        .order_by(ErrataDraft.updated_at.desc(), ErrataDraft.id.desc())
    )
    drafts = result.scalars().all()
    items = []
    for draft in drafts:
        items.append(
            {
                "id": draft.id,
                "arkhamdb_id": draft.arkhamdb_id,
                "status": draft.status.value,
                "participant_usernames": await get_participant_usernames(db, draft.arkhamdb_id),
                "updated_at": draft.updated_at,
            }
        )
    return {"items": items, "total": len(items)}


@router.post("/package")
async def create_review_package(
    body: dict,
    db: AsyncSession = Depends(get_db),
    reviewer: User = Depends(require_reviewer),
):
    arkhamdb_ids = body.get("arkhamdb_ids") or []
    note = body.get("note")
    if not arkhamdb_ids:
        raise HTTPException(status_code=400, detail="请选择要加入勘误包的卡牌")

    await ensure_no_active_package(db)

    result = await db.execute(
        select(ErrataDraft)
        .where(ErrataDraft.arkhamdb_id.in_(arkhamdb_ids))
        .where(ErrataDraft.status == ErrataDraftStatus.ERRATA)
        .where(ErrataDraft.archived_at.is_(None))
        .order_by(ErrataDraft.arkhamdb_id)
    )
    drafts = result.scalars().all()
    found_ids = {draft.arkhamdb_id for draft in drafts}
    missing_ids = [arkhamdb_id for arkhamdb_id in arkhamdb_ids if arkhamdb_id not in found_ids]
    if missing_ids:
        raise HTTPException(status_code=400, detail=f"以下卡牌不在勘误状态：{', '.join(missing_ids)}")

    package = ErrataPackage(package_no=make_package_no(), status=ErrataPackageStatus.WAITING_PUBLISH, created_by=reviewer.id, note=note)
    db.add(package)
    await db.flush()

    for draft in drafts:
        from_status = draft.status.value
        draft.status = ErrataDraftStatus.WAITING_PUBLISH
        draft.package_id = package.id
        draft.updated_by = reviewer.id
        await append_audit_log(
            db,
            draft,
            reviewer,
            ErrataAuditAction.PACKAGE,
            from_status,
            draft.status.value,
            draft.changed_faces,
            "生成勘误包",
        )

    await db.commit()
    await db.refresh(package)
    return {"package": serialize_package(package), "count": len(drafts)}
