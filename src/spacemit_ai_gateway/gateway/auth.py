"""
鉴权模块

支持 X-API-Key 方式鉴权 + IP 白名单
"""

import ipaddress
import logging
from pathlib import Path
from typing import Optional

from fastapi import Request, HTTPException, Depends
from fastapi.security import APIKeyHeader

from ..app.settings import get_settings

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _load_whitelist_file(filepath: str) -> list[str]:
    p = Path(filepath)
    if not p.is_file():
        return []
    entries = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entries.append(line)
    return entries


def _is_ip_whitelisted(client_ip: str, settings) -> bool:
    entries = list(settings.auth.ip_whitelist)
    if settings.auth.ip_whitelist_file:
        entries.extend(_load_whitelist_file(settings.auth.ip_whitelist_file))
    if not entries:
        return False
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for entry in entries:
        try:
            if "/" in entry:
                if addr in ipaddress.ip_network(entry, strict=False):
                    return True
            else:
                if addr == ipaddress.ip_address(entry):
                    return True
        except ValueError:
            continue
    return False


async def verify_api_key(
    request: Request,
    api_key: Optional[str] = Depends(api_key_header)
) -> Optional[str]:
    """
    验证请求是否有权访问。

    优先级：
    1. 鉴权未启用 → 放行
    2. 客户端 IP 在白名单中 → 放行
    3. X-API-Key 有效 → 放行
    4. 否则 → 拒绝
    """
    settings = get_settings()

    if not settings.auth.enabled:
        return None

    client_ip = request.client.host if request.client else ""
    if _is_ip_whitelisted(client_ip, settings):
        return None

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "unauthorized",
                "message": "Missing X-API-Key header"
            }
        )

    if api_key not in settings.auth.api_keys:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "forbidden",
                "message": "Invalid API key"
            }
        )

    return api_key
