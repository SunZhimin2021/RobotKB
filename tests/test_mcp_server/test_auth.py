"""测试 MCPAuth：静态令牌与 JWT 验证。"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

# 统一使用固定 secret 进行测试，不依赖真实 settings
_TEST_SECRET = "test-secret-for-auth-unit"


@pytest.fixture()
def auth():
    """返回以 _TEST_SECRET 为 mcp_token_secret 的 MCPAuth 实例。"""
    from unittest.mock import MagicMock

    mock_settings = MagicMock()
    mock_settings.mcp_token_secret = _TEST_SECRET

    with patch("mcp_server.auth.get_settings", return_value=mock_settings):
        from mcp_server.auth import MCPAuth
        yield MCPAuth()


def test_verify_static_token_wrong(auth):
    """错误的静态 token 返回 False。"""
    assert auth.verify_token("wrong-token-xyz") is False


def test_create_and_verify_jwt(auth):
    """create_token 生成的 JWT 通过 verify_token 验证。"""
    from unittest.mock import MagicMock

    mock_settings = MagicMock()
    mock_settings.mcp_token_secret = _TEST_SECRET

    with patch("mcp_server.auth.get_settings", return_value=mock_settings):
        token = auth.create_token("test-subject")
        assert auth.verify_token(token) is True


def test_expired_jwt_fails(auth):
    """过期的 JWT 返回 False。"""
    from unittest.mock import MagicMock

    mock_settings = MagicMock()
    mock_settings.mcp_token_secret = _TEST_SECRET

    with patch("mcp_server.auth.get_settings", return_value=mock_settings):
        # 生成 expires_in=-1 的已过期 token
        token = auth.create_token("test-subject", expires_in=-1)
        assert auth.verify_token(token) is False


def test_malformed_token_returns_false(auth):
    """乱码 token 不抛异常，返回 False。"""
    assert auth.verify_token("not.a.valid.jwt.at.all!!!") is False
    assert auth.verify_token("") is False
    assert auth.verify_token("随机乱码abc123") is False
