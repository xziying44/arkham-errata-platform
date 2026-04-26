import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.errata_draft import ErrataDraft, ErrataDraftStatus, ErrataPackage, ErrataPackageStatus
from app.models.user import User, UserRole
from app.utils.security import hash_password


async def login_token(client: AsyncClient, username: str, password: str) -> str:
    response = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["token"]


@pytest.mark.asyncio
async def test_reviewer_can_create_unique_package(client: AsyncClient, db):
    reviewer = User(username="reviewer-package", password_hash=hash_password("pw"), role=UserRole.REVIEWER)
    db.add(reviewer)
    await db.commit()
    await db.refresh(reviewer)

    draft1 = ErrataDraft(arkhamdb_id="01001", status=ErrataDraftStatus.ERRATA, original_faces={}, modified_faces={"a": {}}, changed_faces=["a"], created_by=reviewer.id, updated_by=reviewer.id)
    draft2 = ErrataDraft(arkhamdb_id="01002", status=ErrataDraftStatus.ERRATA, original_faces={}, modified_faces={"a": {}}, changed_faces=["a"], created_by=reviewer.id, updated_by=reviewer.id)
    db.add_all([draft1, draft2])
    await db.commit()

    token = await login_token(client, "reviewer-package", "pw")
    response = await client.post(
        "/api/admin/review/package",
        headers={"Authorization": f"Bearer {token}"},
        json={"arkhamdb_ids": ["01001", "01002"], "note": "第一批"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert data["package"]["status"] == "待发布"

    refreshed = (await db.execute(select(ErrataDraft).order_by(ErrataDraft.arkhamdb_id))).scalars().all()
    assert {draft.status for draft in refreshed} == {ErrataDraftStatus.WAITING_PUBLISH}


@pytest.mark.asyncio
async def test_cannot_create_second_active_package(client: AsyncClient, db):
    reviewer = User(username="reviewer-second", password_hash=hash_password("pw"), role=UserRole.REVIEWER)
    db.add(reviewer)
    await db.commit()
    await db.refresh(reviewer)

    active = ErrataPackage(package_no="ERRATA-20260426-001", status=ErrataPackageStatus.WAITING_PUBLISH, created_by=reviewer.id)
    draft = ErrataDraft(arkhamdb_id="01003", status=ErrataDraftStatus.ERRATA, original_faces={}, modified_faces={"a": {}}, changed_faces=["a"], created_by=reviewer.id, updated_by=reviewer.id)
    db.add_all([active, draft])
    await db.commit()

    token = await login_token(client, "reviewer-second", "pw")
    response = await client.post(
        "/api/admin/review/package",
        headers={"Authorization": f"Bearer {token}"},
        json={"arkhamdb_ids": ["01003"]},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "当前已有待发布或发布中的勘误包，请先发布或解锁后再生成新包"


@pytest.mark.asyncio
async def test_admin_unlocks_whole_package(client: AsyncClient, db):
    admin = User(username="admin-unlock", password_hash=hash_password("pw"), role=UserRole.ADMIN)
    db.add(admin)
    await db.commit()
    await db.refresh(admin)

    package = ErrataPackage(package_no="ERRATA-20260426-002", status=ErrataPackageStatus.WAITING_PUBLISH, created_by=admin.id)
    db.add(package)
    await db.flush()
    draft = ErrataDraft(
        arkhamdb_id="01004",
        status=ErrataDraftStatus.WAITING_PUBLISH,
        original_faces={},
        modified_faces={"a": {}},
        changed_faces=["a"],
        package_id=package.id,
        created_by=admin.id,
        updated_by=admin.id,
    )
    db.add(draft)
    await db.commit()

    token = await login_token(client, "admin-unlock", "pw")
    response = await client.post(
        f"/api/admin/packages/{package.id}/unlock",
        headers={"Authorization": f"Bearer {token}"},
        json={"note": "退回修改"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "已退回"

    refreshed = (await db.execute(select(ErrataDraft).where(ErrataDraft.arkhamdb_id == "01004"))).scalar_one()
    assert refreshed.status == ErrataDraftStatus.ERRATA
    assert refreshed.package_id is None
