from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import bcrypt

from app.database import get_db, UserRecord
from app.models import UserCreate, TokenResponse
from app.security import create_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup")
async def signup(user: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserRecord).where(UserRecord.username == user.username))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    hashed = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt()).decode()
    record = UserRecord(username=user.username, hashed_password=hashed)
    db.add(record)
    await db.commit()
    return {"message": f"User {user.username} created successfully"}


@router.post("/token", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(UserRecord).where(UserRecord.username == form.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Wrong username or password")

    token = create_token(user.username)
    return TokenResponse(access_token=token, token_type="bearer")