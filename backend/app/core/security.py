import bcrypt

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
