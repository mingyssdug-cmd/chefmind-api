from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.user.models import User, UserSource

async def get_by_openid(db: AsyncSession, openid: str) -> User | None:
    return (await db.execute(select(User).where(User.openid == openid))).scalar_one_or_none()

async def get_by_username(db: AsyncSession, username: str) -> User | None:
    return (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()

async def get_by_email(db: AsyncSession, email: str) -> User | None:
    return (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()

async def get_by_phone(db: AsyncSession, phone: str) -> User | None:
    return (await db.execute(select(User).where(User.phone == phone))).scalar_one_or_none()

async def get_by_id(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, user_id)

async def create_user(db: AsyncSession, **fields) -> User:
    fields.setdefault("thread_id", uuid.uuid4().hex)
    user = User(**fields)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

async def bind_phone(db: AsyncSession, user: User, phone: str) -> User:
    user.phone = phone
    await db.commit()
    await db.refresh(user)
    return user