from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserRead, UserLogin, Token
from app.middleware.auth import hash_password, verify_password, create_access_token
from app.services.encryption_service import generate_user_salt, generate_per_user_secret

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    # Check uniqueness
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=data.email,
        username=data.username,
        hashed_password=hash_password(data.password),
        encryption_salt=generate_user_salt(),
        # per_user_secret is used by Option B (server deployments) as the sole
        # KDF input material.  Each user has a unique random secret so that
        # the server cannot derive a master key that decrypts all users' data.
        per_user_secret=generate_per_user_secret(),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Account disabled")

    token, expires_in = create_access_token(user.id, user.email)
    return Token(access_token=token, expires_in=expires_in)
