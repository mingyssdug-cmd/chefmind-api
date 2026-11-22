import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserSource(str, enum.Enum):
    wechat = "wechat"
    password = "password"


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 账号密码凭证
    username: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # 微信登录凭证
    openid: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)

    # 手机号
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, index=True, nullable=True)

    # 用户资料
    nickname: Mapped[str | None] = mapped_column(String(128), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # 专属会话线程
    thread_id: Mapped[str] = mapped_column(String(64), nullable=False, default=lambda: uuid.uuid4().hex)

    source: Mapped[UserSource] = mapped_column(Enum(UserSource, native_enum=False, length=20),
                                               default=UserSource.password)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())