from __future__ import annotations
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import TokenError, decode_token
from app.modules.user import crud
from app.modules.user.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)
_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="未授权，请先登录",
    headers={"WWW-Authenticate": "Bearer"},
)

async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not token:
        raise _credentials_exc
    try:
        payload = decode_token(token, expected_type="access")
    except TokenError:
        raise _credentials_exc

    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        raise _credentials_exc

    user = await crud.get_by_id(db, user_id)
    if user is None or not user.is_active:
        raise _credentials_exc
    return user