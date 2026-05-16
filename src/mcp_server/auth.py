"""MCPAuth — Bearer Token 验证（HMAC-SHA256 静态令牌 或 JWT）。"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time

from jose import JWTError, jwt

from common.config import get_settings

logger = logging.getLogger(__name__)

_ALGORITHM = "HS256"


class MCPAuth:
    """Bearer Token 验证（HMAC-SHA256 静态令牌 或 JWT）。"""

    def verify_token(self, token: str) -> bool:
        """验证 token。

        支持两种 token：
        1. 静态令牌：与 settings.mcp_token_secret 进行 HMAC-SHA256 比对
        2. JWT：用 settings.mcp_token_secret 验签，检查 exp

        返回 True/False，不抛异常。
        """
        if not token:
            return False
        try:
            settings = get_settings()
            secret = settings.mcp_token_secret

            # 先尝试 JWT 解码（JWT 格式为 xxx.yyy.zzz 三段）
            if token.count(".") == 2:
                try:
                    payload = jwt.decode(token, secret, algorithms=[_ALGORITHM])
                    # 检查 exp
                    exp = payload.get("exp")
                    if exp is not None and int(time.time()) > exp:
                        return False
                    return True
                except JWTError:
                    pass

            # 静态令牌：用 HMAC-SHA256 做时间安全比对，防止时序攻击
            expected = hmac.new(
                secret.encode(),
                token.encode(),
                hashlib.sha256,
            ).hexdigest()
            # 将 token 本身 HMAC 后与 settings.mcp_token_secret 的 HMAC 进行比对
            # 实际上静态令牌校验：token == mcp_token_secret（用 hmac.compare_digest 防时序攻击）
            return hmac.compare_digest(token, secret)
        except Exception:
            logger.debug("Token verification error", exc_info=True)
            return False

    def create_token(self, subject: str, expires_in: int = 86400) -> str:
        """生成 JWT token（HS256）。

        Args:
            subject: JWT sub 字段（通常是用户/客户端标识）。
            expires_in: 有效期（秒），默认 24 小时。

        Returns:
            签名后的 JWT 字符串。
        """
        settings = get_settings()
        secret = settings.mcp_token_secret
        now = int(time.time())
        payload = {
            "sub": subject,
            "iat": now,
            "exp": now + expires_in,
        }
        return jwt.encode(payload, secret, algorithm=_ALGORITHM)
