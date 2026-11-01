"""JWT-токены доступа. Токен ссылается на серверную сессию (sid), поэтому её можно отозвать."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import jwt

ALGORITHM = "HS256"


def create_access_token(secret_key: str, user_id: int, session_id: int, expires_at: datetime) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "sid": session_id,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, secret_key, algorithm=ALGORITHM)


def decode_access_token(secret_key: str, token: str) -> dict[str, Any] | None:
    """Возвращает полезную нагрузку или None, если токен недействителен или истёк."""
    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub", "sid"]},
        )
    except jwt.PyJWTError:
        return None
    try:
        payload["user_id"] = int(payload["sub"])
        payload["sid"] = int(payload["sid"])
    except (TypeError, ValueError):
        return None
    return payload
