from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User, UserRole
from app.schemas.user import (
    LoginRequest,
    LoginResponse,
    CreateUserRequest,
    ResetPasswordRequest,
    UpdateUserRequest,
    UserResponse,
)
from app.utils.security import hash_password, verify_password, create_access_token, decode_token

router = APIRouter(prefix="/api/auth", tags=["认证"])
security_scheme = HTTPBearer()


async def require_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=401, detail="无效的认证令牌")
    result = await db.execute(select(User).where(User.id == payload["user_id"]))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    return user


async def require_admin(current_user: User = Depends(require_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user


async def require_reviewer(current_user: User = Depends(require_user)) -> User:
    if current_user.role not in {UserRole.REVIEWER, UserRole.ADMIN}:
        raise HTTPException(status_code=403, detail="需要审核权限")
    return current_user


async def require_errata_user(current_user: User = Depends(require_user)) -> User:
    if current_user.role not in {UserRole.ERRATA, UserRole.ADMIN}:
        raise HTTPException(status_code=403, detail="需要勘误权限")
    return current_user


def parse_user_role(role: str) -> UserRole:
    try:
        return UserRole(role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="无效的用户角色") from exc


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已被禁用")
    token = create_access_token(user.id, user.role.value)
    return LoginResponse(token=token, user_id=user.id, username=user.username, role=user.role.value)


@router.get("/me", response_model=UserResponse)
async def get_current_user(current_user: User = Depends(require_user)):
    return current_user


@router.post("/users", response_model=UserResponse)
async def create_user(
    req: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    existing = await db.execute(select(User).where(User.username == req.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(username=req.username, password_hash=hash_password(req.password), role=parse_user_role(req.role), note=req.note.strip())
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(select(User).order_by(User.id))
    return result.scalars().all()


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    req: UpdateUserRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if req.role is not None:
        user.role = parse_user_role(req.role)
    if req.is_active is not None:
        user.is_active = req.is_active
    if req.note is not None:
        user.note = req.note.strip()
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    req: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.password_hash = hash_password(req.password)
    await db.commit()
    return {"ok": True}
