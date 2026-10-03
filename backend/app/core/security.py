from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.errors import UnauthorizedError

# bcrypt обрабатывает только первые 72 байта; длиннее — явно отклоняем,
# чтобы два разных длинных пароля не давали одинаковый хеш.
_MAX_PASSWORD_BYTES = 72


def hash_password(password: str, *, rounds: int = 12) -> str:
    raw = password.encode()
    if len(raw) > _MAX_PASSWORD_BYTES:
        raise ValueError("password is too long")
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=rounds)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    raw = password.encode()
    if len(raw) > _MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw, password_hash.encode())
    except ValueError:  # битый хеш
        return False


# --- JWT ---


def create_access_token(
    *, user_id: str, role: str, secret: str, ttl_min: int, algorithm: str = "HS256"
) -> str:
    now = datetime.now(UTC)
    payload = {"sub": user_id, "role": role, "iat": now, "exp": now + timedelta(minutes=ttl_min)}
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_access_token(token: str, *, secret: str, algorithm: str = "HS256") -> dict[str, Any]:
    """Возвращает claims или бросает UnauthorizedError (просрочен, подделан, битый)."""
    try:
        return jwt.decode(
            token, secret, algorithms=[algorithm], options={"require": ["sub", "exp"]}
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid token") from exc
