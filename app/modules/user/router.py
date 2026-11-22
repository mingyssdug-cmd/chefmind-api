from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import TokenError, create_access_token, create_bind_ticket, create_refresh_token, decode_token, \
    hash_password, verify_password
from app.modules.user import crud
from app.modules.user.deps import get_current_user
from app.modules.user.models import User, UserSource
from app.modules.user.schemas import (
    BindPhoneRequest, LoginRequest, LogoutRequest, RefreshRequest,
    RegisterRequest, TokenPair, UserOut, WechatLoginRequest
)
from app.core import wechat

router = APIRouter(prefix="/auth", tags=["auth"])
_optional_bearer = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def _token_pair(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=UserOut.model_validate(user),
    )


@router.post("/wechat/login", response_model=TokenPair, summary="微信静默登录")
async def wechat_login(req: WechatLoginRequest, db: AsyncSession = Depends(get_db)):
    wx_data = await wechat.code2session(req.code)
    openid = wx_data["openid"]
    user = await crud.get_by_openid(db, openid)

    if user is None:
        user = User(
            openid=openid, nickname=req.nickname,
            avatar_url=req.avatar_url, source=UserSource.wechat, thread_id=__import__("uuid").uuid4().hex
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    pair = _token_pair(user)
    if not user.phone:
        pair.need_bind_phone = True
        pair.bind_ticket = create_bind_ticket(openid)
    return pair


@router.post("/wechat/bind-phone", response_model=TokenPair, summary="微信手机号绑定")
async def wechat_bind_phone(
        req: BindPhoneRequest,
        bearer: str | None = Depends(_optional_bearer),
        db: AsyncSession = Depends(get_db),
):
    target: User | None = None
    if bearer:
        try:
            payload = decode_token(bearer, expected_type="access")
            target = await crud.get_by_id(db, int(payload["sub"]))
        except (TokenError, ValueError, KeyError):
            target = None

    if target is None:
        if not req.bind_ticket:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录或携带 bind_ticket")
        try:
            payload = decode_token(req.bind_ticket, expected_type="bind")
        except TokenError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="绑定票据无效或已过期")
        openid = payload["sub"]
        target = await crud.get_by_openid(db, openid)

    phone = await wechat.get_user_phone(req.phone_code)

    # 手机号全局唯一校验
    holder = await crud.get_by_phone(db, phone)
    if holder is not None and holder.id != target.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该手机号已绑定其他账号")

    await crud.bind_phone(db, target, phone)
    return _token_pair(target)


@router.post("/register", response_model=UserOut, status_code=201, summary="账号密码注册")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    if await crud.get_by_username(db, req.username) is not None:
        raise HTTPException(status_code=409, detail="用户名已存在")
    if req.email and await crud.get_by_email(db, req.email) is not None:
        raise HTTPException(status_code=409, detail="邮箱已被注册")

    user = await crud.create_user(
        db, username=req.username, email=req.email,
        hashed_password=hash_password(req.password), source=UserSource.password
    )
    return UserOut.model_validate(user)


# 顶部导入表单模型
from fastapi.security import OAuth2PasswordRequestForm


# 找到 @router.post("/login" ...) 这个接口，替换为：
@router.post("/login", response_model=TokenPair, summary="账号密码登录")
async def login(
        form_data: OAuth2PasswordRequestForm = Depends(),  # 改为接收表单
        db: AsyncSession = Depends(get_db),
):
    # 表单里 username 会存到 form_data.username，密码在 form_data.password
    user = await crud.get_by_username(db, form_data.username) or await crud.get_by_email(db, form_data.username)

    # 注意这里也要改成 form_data.password
    if user is None or not user.hashed_password or not verify_password(user.hashed_password, form_data.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return _token_pair(user)


@router.post("/refresh", response_model=TokenPair, summary="刷新令牌")
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(req.refresh_token, expected_type="refresh")
    except TokenError:
        raise HTTPException(status_code=401, detail="刷新令牌无效")
    user = await crud.get_by_id(db, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    return _token_pair(user)


@router.get("/me", response_model=UserOut, summary="获取当前用户")
async def me(current: User = Depends(get_current_user)):
    return UserOut.model_validate(current)


@router.post("/logout", status_code=204, summary="登出")
async def logout():
    return Response(status_code=status.HTTP_204_NO_CONTENT)