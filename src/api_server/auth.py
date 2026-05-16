"""RBAC JWT authentication for the API server."""
from __future__ import annotations

import time
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

_ALGORITHM = "HS256"
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


class RBACToken(BaseModel):
    sub: str   # user id
    role: str  # admin|reviewer|importer|viewer
    exp: int


class Auth:
    ROLE_HIERARCHY: dict[str, int] = {
        "admin": 4,
        "reviewer": 3,
        "importer": 2,
        "viewer": 1,
    }

    def __init__(self, secret: str) -> None:
        self._secret = secret

    def create_token(self, user_id: str, role: str, expires_in: int = 86400) -> str:
        """Encode a signed JWT with sub, role, and exp claims."""
        now = int(time.time())
        payload: dict[str, Any] = {
            "sub": user_id,
            "role": role,
            "exp": now + expires_in,
            "iat": now,
        }
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM)

    def verify_token(self, token: str) -> RBACToken:
        """Decode and validate JWT.  Raises HTTPException(401) on failure."""
        try:
            payload = jwt.decode(token, self._secret, algorithms=[_ALGORITHM])
        except JWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid or expired token: {exc}",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        sub = payload.get("sub")
        role = payload.get("role")
        exp = payload.get("exp")

        if sub is None or role is None or exp is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing required claims",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if role not in self.ROLE_HIERARCHY:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Unknown role: {role}",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return RBACToken(sub=sub, role=role, exp=int(exp))

    def require_role(self, min_role: str):
        """FastAPI Depends factory: check that the token role >= min_role."""
        auth_self = self

        async def checker(token: str | None = Depends(_oauth2_scheme)) -> RBACToken:
            if token is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            rbac = auth_self.verify_token(token)
            required_level = auth_self.ROLE_HIERARCHY.get(min_role, 0)
            user_level = auth_self.ROLE_HIERARCHY.get(rbac.role, 0)
            if user_level < required_level:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Role '{rbac.role}' insufficient; requires '{min_role}' or higher",
                )
            return rbac

        return checker
