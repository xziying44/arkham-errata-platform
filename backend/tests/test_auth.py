import pytest
from httpx import AsyncClient
from app.models.user import User, UserRole
from app.utils.security import hash_password

@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, db):
    user = User(username="admin", password_hash=hash_password("123456"), role=UserRole.ADMIN)
    db.add(user)
    await db.commit()
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "123456"})
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert data["role"] == "管理员"

@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, db):
    user = User(username="admin2", password_hash=hash_password("123456"), role=UserRole.ADMIN)
    db.add(user)
    await db.commit()
    resp = await client.post("/api/auth/login", json={"username": "admin2", "password": "wrong"})
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_create_user_duplicate(client: AsyncClient, db):
    user = User(username="editor1", password_hash="hash", role=UserRole.USER)
    admin = User(username="duplicate_admin", password_hash=hash_password("123456"), role=UserRole.ADMIN)
    db.add_all([user, admin])
    await db.commit()
    login_resp = await client.post(
        "/api/auth/login",
        json={"username": "duplicate_admin", "password": "123456"},
    )
    token = login_resp.json()["token"]
    resp = await client.post(
        "/api/auth/users",
        json={"username": "editor1", "password": "pass"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_user_requires_admin(client: AsyncClient):
    resp = await client.post(
        "/api/auth/users",
        json={"username": "unauthorized_admin", "password": "pass", "role": "管理员"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_admin_can_create_user_and_list_users(client: AsyncClient, db):
    admin = User(
        username="admin_for_user_mgmt",
        password_hash=hash_password("123456"),
        role=UserRole.ADMIN,
    )
    db.add(admin)
    await db.commit()

    login_resp = await client.post(
        "/api/auth/login",
        json={"username": "admin_for_user_mgmt", "password": "123456"},
    )
    token = login_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        "/api/auth/users",
        json={"username": "created_by_admin", "password": "pass", "role": "用户"},
        headers=headers,
    )
    assert create_resp.status_code == 200

    list_resp = await client.get("/api/auth/users", headers=headers)
    assert list_resp.status_code == 200
    assert any(u["username"] == "created_by_admin" for u in list_resp.json())


@pytest.mark.asyncio
async def test_me_returns_current_user(client: AsyncClient, db):
    user = User(
        username="me_admin",
        password_hash=hash_password("123456"),
        role=UserRole.ADMIN,
    )
    db.add(user)
    await db.commit()

    login_resp = await client.post(
        "/api/auth/login",
        json={"username": "me_admin", "password": "123456"},
    )
    token = login_resp.json()["token"]

    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "me_admin"
    assert resp.json()["role"] == "管理员"
