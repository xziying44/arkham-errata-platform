from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User, UserRole
from app.schemas.user import LoginRequest, LoginResponse, CreateUserRequest, UserResponse
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
    role = UserRole.ADMIN if req.role == "管理员" else UserRole.USER
    user = User(username=req.username, password_hash=hash_password(req.password), role=role)
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
