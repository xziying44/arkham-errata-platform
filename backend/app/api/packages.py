"""勘误包 API - 管理员审阅、解锁和完成发布"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_admin
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

router = APIRouter(prefix="/api/admin/packages", tags=["勘误包"])


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


def serialize_draft(draft: ErrataDraft, participants: list[str]) -> dict:
    return {
        "id": draft.id,
        "arkhamdb_id": draft.arkhamdb_id,
        "status": draft.status.value,
        "changed_faces": draft.changed_faces,
        "package_id": draft.package_id,
        "participant_usernames": participants,
        "updated_at": draft.updated_at,
    }


async def load_package(db: AsyncSession, package_id: int) -> ErrataPackage:
    package = await db.get(ErrataPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="勘误包不存在")
    return package


async def load_package_drafts(db: AsyncSession, package_id: int) -> list[ErrataDraft]:
    result = await db.execute(
        select(ErrataDraft).where(ErrataDraft.package_id == package_id).order_by(ErrataDraft.arkhamdb_id)
    )
    return list(result.scalars().all())


@router.get("")
async def list_packages(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(select(ErrataPackage).order_by(ErrataPackage.created_at.desc(), ErrataPackage.id.desc()))
    return {"items": [serialize_package(package) for package in result.scalars().all()]}


@router.get("/{package_id}")
async def get_package_detail(
    package_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    package = await load_package(db, package_id)
    drafts = await load_package_drafts(db, package_id)
    return {
        "package": serialize_package(package),
        "drafts": [
            serialize_draft(draft, await get_participant_usernames(db, draft.arkhamdb_id))
            for draft in drafts
        ],
    }


@router.post("/{package_id}/unlock")
async def unlock_package(
    package_id: int,
    body: dict | None = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    package = await load_package(db, package_id)
    if package.status != ErrataPackageStatus.WAITING_PUBLISH:
        raise HTTPException(status_code=409, detail="只有待发布的勘误包可以解锁")
    note = (body or {}).get("note")
    drafts = await load_package_drafts(db, package_id)

    package.status = ErrataPackageStatus.UNLOCKED
    package.unlocked_by = admin.id
    package.note = note
    for draft in drafts:
        from_status = draft.status.value
        draft.status = ErrataDraftStatus.ERRATA
        draft.package_id = None
        draft.updated_by = admin.id
        await append_audit_log(
            db,
            draft,
            admin,
            ErrataAuditAction.UNLOCK,
            from_status,
            draft.status.value,
            draft.changed_faces,
            note or "管理员解锁整包",
        )
    await db.commit()
    await db.refresh(package)
    return serialize_package(package)


@router.post("/{package_id}/complete")
async def complete_package(
    package_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    package = await load_package(db, package_id)
    if package.status not in {ErrataPackageStatus.WAITING_PUBLISH, ErrataPackageStatus.PUBLISHING}:
        raise HTTPException(status_code=409, detail="只有待发布或发布中的勘误包可以完成发布")
    drafts = await load_package_drafts(db, package_id)

    package.status = ErrataPackageStatus.PUBLISHED
    package.published_by = admin.id
    package.published_at = datetime.now()
    for draft in drafts:
        from_status = draft.status.value
        draft.status = ErrataDraftStatus.ARCHIVED
        draft.archived_at = datetime.now()
        draft.updated_by = admin.id
        await append_audit_log(
            db,
            draft,
            admin,
            ErrataAuditAction.PUBLISH,
            from_status,
            draft.status.value,
            draft.changed_faces,
            "发布完成",
        )
    await db.commit()
    await db.refresh(package)
    return serialize_package(package)
