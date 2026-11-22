"""
微信服务端API封装与AccessToken缓存
"""
import asyncio
import time
import httpx
from app.core.config import settings

_JSCODE2SESSION = "https://api.weixin.qq.com/sns/jscode2session"
_PHONE_URL = "https://api.weixin.qq.com/wxa/business/getuserphonenumber"
_STABLE_TOKEN = "https://api.weixin.qq.com/cgi-bin/stable_token"

_token_cache = {"value": "", "expire_at": 0.0}
_token_lock = asyncio.Lock()


class WechatError(Exception):
    pass


async def code2session(code: str) -> dict:
    params = {
        "appid": settings.WECHAT_APPID,
        "secret": settings.WECHAT_SECRET,
        "js_code": code,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(_JSCODE2SESSION, params=params)
        data = resp.json()
    if "openid" not in data:
        raise WechatError(f"code2Session 失败: {data}")
    return data


async def _get_access_token() -> str:
    now = time.time()
    if _token_cache["value"] and now < float(_token_cache["expire_at"]):
        return str(_token_cache["value"])

    async with _token_lock:
        now = time.time()
        if _token_cache["value"] and now < float(_token_cache["expire_at"]):
            return str(_token_cache["value"])

        body = {"grant_type": "client_credential", "appid": settings.WECHAT_APPID, "secret": settings.WECHAT_SECRET}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(_STABLE_TOKEN, json=body)
            data = resp.json()

        if "access_token" not in data:
            raise WechatError(f"获取 access_token 失败: {data}")

        _token_cache["value"] = data["access_token"]
        _token_cache["expire_at"] = time.time() + int(data.get("expires_in", 7200)) - 200
        return str(_token_cache["value"])


async def get_user_phone(phone_code: str) -> str:
    access_token = await _get_access_token()
    url = f"{_PHONE_URL}?access_token={access_token}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json={"code": phone_code})
        data = resp.json()

    if data.get("errcode") != 0:
        raise WechatError(f"获取手机号失败: {data}")

    phone_info = data.get("phone_info") or {}
    phone = phone_info.get("purePhoneNumber") or phone_info.get("phoneNumber")
    if not phone:
        raise WechatError(f"手机号为空")
    return phone