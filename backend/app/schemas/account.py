from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.domain.enums import NotificationChannel, Role
from app.services.account import AccountView


class AccountOut(BaseModel):
    id: str
    role: Role
    full_name: str
    email: str
    specialty: str | None
    # Только у пациента
    birth_date: date | None = None
    phone: str | None = None
    contact_email: str | None = None  # почта для уведомлений, если не совпадает с email входа
    notify_channels: list[NotificationChannel] = []
    available_channels: list[NotificationChannel] = []  # есть контакт для канала

    @classmethod
    def build(cls, v: AccountView) -> AccountOut:
        u, p = v.user, v.patient
        return cls(
            id=u.id,
            role=u.role,
            full_name=u.full_name,
            email=u.email,
            specialty=u.specialty,
            birth_date=p.birth_date if p else None,
            phone=p.phone if p else None,
            contact_email=p.contact_email if p else None,
            notify_channels=[c for c in NotificationChannel if p and c in p.notify_channels],
            available_channels=list(v.available_channels),
        )


class AccountPatch(BaseModel):
    email: str | None = None
    phone: str | None = None
    contact_email: str | None = None  # "" — уведомления на email входа
    notify_channels: list[NotificationChannel] | None = None


class PasswordIn(BaseModel):
    old_password: str
    new_password: str
