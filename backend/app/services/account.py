"""Личный кабинет: профиль, контакты, каналы уведомлений, смена пароля."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import ConflictError, InvalidInputError
from app.core.security import hash_password, verify_password
from app.domain import rules
from app.domain.enums import NotificationChannel, Role
from app.domain.models import Patient, Social, User
from app.services import audit
from app.store import Store

MIN_PASSWORD = 4  # демо: без требований к сложности


@dataclass(slots=True)
class AccountView:
    user: User
    patient: Patient | None
    available_channels: tuple[NotificationChannel, ...]


def _clean_socials(items: list[Social]) -> tuple[Social, ...]:
    """Пустые адреса отбрасываем, повторы (сеть + адрес) схлопываем."""
    seen: dict[tuple[str, str], Social] = {}
    for s in items:
        handle = s.handle.strip()
        if handle:
            seen.setdefault((s.network, handle.lower()), Social(s.network, handle))
    return tuple(seen.values())


class AccountService:
    def __init__(self, store: Store) -> None:
        self.store = store

    def view(self, user: User) -> AccountView:
        patient = self.store.patient_by_user(user.id) if user.role is Role.PATIENT else None
        channels = rules.available_channels(patient, user) if patient else ()
        return AccountView(user=user, patient=patient, available_channels=channels)

    def update(
        self,
        user: User,
        *,
        email: str | None = None,
        phone: str | None = None,
        contact_email: str | None = None,
        socials: list[Social] | None = None,
        notify_channels: list[NotificationChannel] | None = None,
    ) -> AccountView:
        """Контакты меняет сам пользователь; ФИО и специальность врача — главврач."""
        changes: dict[str, object] = {}
        if email is not None and email.strip().lower() != user.email:
            email = email.strip().lower()
            if "@" not in email:
                raise InvalidInputError("Некорректный email")
            if self.store.user_by_email(email):
                raise ConflictError("Этот email уже занят")
            user.email = changes["email"] = email
        patient = self.store.patient_by_user(user.id) if user.role is Role.PATIENT else None
        if patient is None and (
            phone is not None or contact_email is not None or socials is not None or notify_channels
        ):
            raise InvalidInputError("Телефон и каналы уведомлений — только у пациента")
        if patient is not None:
            if phone is not None and phone.strip() != patient.phone:
                if not phone.strip():
                    raise InvalidInputError("Телефон нужен для связи с клиникой")
                patient.phone = changes["phone"] = phone.strip()
            if contact_email is not None:
                clean_email = contact_email.strip().lower() or None
                if clean_email is not None and "@" not in clean_email:
                    raise InvalidInputError("Некорректный email для уведомлений")
                if clean_email != patient.contact_email:
                    patient.contact_email = changes["contact_email"] = clean_email
            if socials is not None:
                clean = _clean_socials(socials)
                if clean != patient.socials:
                    patient.socials = clean
                    changes["socials"] = [str(s.network) for s in clean]
            if notify_channels is not None:
                chosen = frozenset(notify_channels)
                if chosen != patient.notify_channels:
                    patient.notify_channels = chosen
                    changes["notify_channels"] = sorted(str(c) for c in chosen)
        if changes:
            audit.record(
                self.store,
                user,
                "account.updated",
                target_type="user",
                target_id=user.id,
                fields=sorted(changes),
            )
        return self.view(user)

    def change_password(self, user: User, *, old: str, new: str) -> None:
        if not verify_password(old, user.password_hash):
            raise InvalidInputError("Текущий пароль указан неверно")
        if len(new) < MIN_PASSWORD:
            raise InvalidInputError(f"Новый пароль — не короче {MIN_PASSWORD} символов")
        user.password_hash = hash_password(new, rounds=4)
        audit.record(
            self.store, user, "account.password_changed", target_type="user", target_id=user.id
        )
