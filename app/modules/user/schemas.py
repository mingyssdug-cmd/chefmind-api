from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.modules.user.models import UserSource

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str | None = None
    email: str | None = None
    phone: str | None = None
    nickname: str | None = None
    avatar_url: str | None = None
    source: UserSource
    is_active: bool
    created_at: datetime

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    need_bind_phone: bool = False
    bind_ticket: str | None = None
    user: UserOut

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    email: EmailStr | None = None

class LoginRequest(BaseModel):
    username: str = Field(description="用户名或邮箱")
    password: str = Field(min_length=1)

class WechatLoginRequest(BaseModel):
    code: str = Field(description="wx.login 返回的 code")
    nickname: str | None = None
    avatar_url: str | None = None

class BindPhoneRequest(BaseModel):
    phone_code: str = Field(description="getPhoneNumber 返回的 code")
    bind_ticket: str | None = None

class RefreshRequest(BaseModel):
    refresh_token: str

class LogoutRequest(BaseModel):
    refresh_token: str | None = None