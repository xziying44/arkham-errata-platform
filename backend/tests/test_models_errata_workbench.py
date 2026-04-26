import pytest
from sqlalchemy import select

from app.models.errata_draft import ErrataDraft, ErrataDraftStatus, ErrataPackage, ErrataPackageStatus
from app.models.user import User, UserRole
from app.utils.security import hash_password


@pytest.mark.asyncio
async def test_create_errata_draft_with_faces(db):
    user = User(username="draft-model-user", password_hash=hash_password("pw"), role=UserRole.ERRATA)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    draft = ErrataDraft(
        arkhamdb_id="01001",
        status=ErrataDraftStatus.ERRATA,
        original_faces={"a": {"name": "旧正面"}, "b": {"name": "旧背面"}},
        modified_faces={"a": {"name": "新正面"}, "b": {"name": "旧背面"}},
        changed_faces=["a"],
        created_by=user.id,
        updated_by=user.id,
    )
    db.add(draft)
    await db.commit()

    result = await db.execute(select(ErrataDraft).where(ErrataDraft.arkhamdb_id == "01001"))
    saved = result.scalar_one()

    assert saved.status == ErrataDraftStatus.ERRATA
    assert saved.modified_faces["a"]["name"] == "新正面"
    assert saved.changed_faces == ["a"]


@pytest.mark.asyncio
async def test_create_waiting_publish_package(db):
    user = User(username="package-model-user", password_hash=hash_password("pw"), role=UserRole.REVIEWER)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    package = ErrataPackage(package_no="ERRATA-20260426-001", status=ErrataPackageStatus.WAITING_PUBLISH, created_by=user.id)
    db.add(package)
    await db.commit()

    result = await db.execute(select(ErrataPackage).where(ErrataPackage.package_no == "ERRATA-20260426-001"))
    saved = result.scalar_one()

    assert saved.status == ErrataPackageStatus.WAITING_PUBLISH
