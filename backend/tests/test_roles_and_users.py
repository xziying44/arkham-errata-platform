import pytest
from httpx import AsyncClient

from app.models.user import User, UserRole
from app.utils.security import hash_password


@pytest.mark.asyncio
async def test_admin_can_create_reviewer(client: AsyncClient, db):
    admin = User(username="admin-role-test", password_hash=hash_password("pw"), role=UserRole.ADMIN)
    db.add(admin)
    await db.commit()

    login = await client.post("/api/auth/login", json={"username": "admin-role-test", "password": "pw"})
    token = login.json()["token"]

    response = await client.post(
        "/api/auth/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "reviewer-a", "password": "pw2", "role": "审核员"},
    )

    assert response.status_code == 200
    assert response.json()["username"] == "reviewer-a"
    assert response.json()["role"] == "审核员"


@pytest.mark.asyncio
async def test_errata_user_cannot_list_users(client: AsyncClient, db):
    user = User(username="errata-role-test", password_hash=hash_password("pw"), role=UserRole.ERRATA)
    db.add(user)
    await db.commit()

    login = await client.post("/api/auth/login", json={"username": "errata-role-test", "password": "pw"})
    token = login.json()["token"]

    response = await client.get("/api/auth/users", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.json()["detail"] == "需要管理员权限"


@pytest.mark.asyncio
async def test_admin_can_disable_and_reset_password(client: AsyncClient, db):
    admin = User(username="admin-user-mgmt", password_hash=hash_password("pw"), role=UserRole.ADMIN)
    target = User(username="target-user", password_hash=hash_password("old"), role=UserRole.ERRATA)
    db.add_all([admin, target])
    await db.commit()
    await db.refresh(target)

    login = await client.post("/api/auth/login", json={"username": "admin-user-mgmt", "password": "pw"})
    token = login.json()["token"]

    patch = await client.patch(
        f"/api/auth/users/{target.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "审核员", "is_active": False},
    )
    assert patch.status_code == 200
    assert patch.json()["role"] == "审核员"
    assert patch.json()["is_active"] is False

    reset = await client.post(
        f"/api/auth/users/{target.id}/reset-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": "new-password"},
    )
    assert reset.status_code == 200
    assert reset.json()["ok"] is True
