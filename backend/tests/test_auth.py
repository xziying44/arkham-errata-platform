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
    db.add(user)
    await db.commit()
    resp = await client.post("/api/auth/users", json={"username": "editor1", "password": "pass"})
    assert resp.status_code == 400
