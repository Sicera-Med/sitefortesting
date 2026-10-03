from __future__ import annotations

from app.core.config import Settings
from app.core.errors import UnauthorizedError
from app.core.security import create_access_token, decode_access_token, verify_password
from app.domain.enums import Role
from app.domain.models import Patient, User
from app.services import audit
from app.store import Store


class AuthService:
    def __init__(self, store: Store, settings: Settings) -> None:
        self.store = store
        self.settings = settings

    def login(self, email: str, password: str) -> tuple[str, User]:
        user = self.store.user_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            audit.record(
                self.store, None, "auth.login_failed", target_type="auth", target_id=email.lower()
            )
            raise UnauthorizedError("Неверный email или пароль")
        token = create_access_token(
            user_id=user.id,
            role=str(user.role),
            secret=self.settings.JWT_SECRET,
            ttl_min=self.settings.JWT_TTL_MIN,
            algorithm=self.settings.JWT_ALGORITHM,
        )
        audit.record(self.store, user, "auth.login", target_type="user", target_id=user.id)
        return token, user

    def user_from_token(self, token: str) -> User:
        claims = decode_access_token(
            token, secret=self.settings.JWT_SECRET, algorithm=self.settings.JWT_ALGORITHM
        )
        user = self.store.get_user(claims["sub"])
        if user is None:
            raise UnauthorizedError("User no longer exists")
        return user

    def patient_profile(self, user: User) -> Patient | None:
        return self.store.patient_by_user(user.id) if user.role is Role.PATIENT else None

    def demo_accounts(self) -> list[User]:
        order = {Role.DOCTOR: 0, Role.HEAD: 1, Role.PATIENT: 2}
        return sorted(self.store.users.values(), key=lambda u: (order[u.role], u.full_name))
