"""Доменные сущности. Чистый Python, без зависимостей от фреймворков.

Изменяемые сущности (Study, Notification) — обычные dataclass'ы;
неизменяемые (AIInference, AuditEvent) — frozen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.domain.enums import (
    AISource,
    AppointmentStatus,
    DeliveryStatus,
    NotificationChannel,
    NotificationStatus,
    PatientActionType,
    RecommendationType,
    Role,
    Sex,
    SocialNetwork,
    StudyStatus,
    StudyType,
)
from app.domain.sr import SRField, report_text


@dataclass(slots=True, kw_only=True)
class User:
    id: str
    role: Role
    email: str
    password_hash: str
    full_name: str
    # Профиль врача упрощён до одного поля (у главврача и менеджера — None)
    specialty: str | None = None
    active: bool = True  # главврач может отключить доступ врача


@dataclass(frozen=True, slots=True)
class Social:
    """Аккаунт пациента в соцсети или мессенджере."""

    network: SocialNetwork
    handle: str


@dataclass(slots=True, kw_only=True)
class Patient:
    id: str
    user_id: str
    full_name: str
    birth_date: date
    sex: Sex
    phone: str
    contact_email: str | None = None  # почта для уведомлений; нет — email входа
    socials: tuple[Social, ...] = ()  # соцсети и мессенджеры, которые указал пациент
    # Каналы, в которые пациент разрешил уведомления (кабинет на сайте — всегда)
    notify_channels: frozenset[NotificationChannel] = frozenset(NotificationChannel)

    def age_on(self, day: date) -> int:
        before_birthday = (day.month, day.day) < (self.birth_date.month, self.birth_date.day)
        return day.year - self.birth_date.year - int(before_birthday)


@dataclass(slots=True, kw_only=True)
class Study:
    id: str
    patient_id: str
    treating_doctor_id: str
    study_type: StudyType
    body_region: str
    status: StudyStatus
    performed_at: datetime
    created_at: datetime
    # Раздел «Описание» DICOM SR (поля БФТ как есть) и заключение рентгенолога, если есть
    sr_fields: tuple[SRField, ...] = ()
    conclusion: str | None = None
    # Автоповтор при сбое AI: неудачных автоматических попыток подряд, когда следующая,
    # и остановлен ли он (после AI_MAX_AUTO_ATTEMPTS — только ручная отправка)
    ai_auto_failures: int = 0
    ai_next_retry_at: datetime | None = None
    ai_auto_stopped: bool = False

    @property
    def report_text(self) -> str:
        """Протокол для AI в формате AI-команды: «Описание: …\nЗаключение: …»."""
        return report_text(self.sr_fields, self.conclusion)


@dataclass(frozen=True, slots=True)
class RankedOption:
    type: RecommendationType
    score: float | None  # None — модель дала только порядок вариантов


@dataclass(frozen=True, slots=True)
class Reason:
    code: str
    label: str
    weight: float | None  # None — модель не оценивает вес, порядок = важность


@dataclass(frozen=True, slots=True, kw_only=True)
class AIInference:
    id: str
    study_id: str
    source: AISource
    request_id: str
    model_name: str
    model_version: str
    recommendation: RecommendationType
    confidence: float | None  # None — модель не сообщает уверенность
    ranked_options: tuple[RankedOption, ...]
    reasons: tuple[Reason, ...]
    latency_ms: int
    created_at: datetime
    # Предложенные AI детали основного варианта: {"specialists"} / {"research_types"}; {} — нет
    details: dict[str, Any] = field(default_factory=dict)
    # Все варианты модели (основной первым): пункты с причиной, сроком и ссылками на документы
    options: tuple[dict[str, Any], ...] = ()
    guidelines_mode: str | None = None  # справочник: по словам протокола / весь


@dataclass(slots=True, kw_only=True)
class Decision:
    id: str
    study_id: str
    doctor_id: str
    # Врач выбирает от одного до всех трёх вариантов
    chosen_types: tuple[RecommendationType, ...]
    details: dict[str, Any]
    comment: str | None
    # Снапшот AI на момент решения (None — решение принято без AI)
    ai_inference_id: str | None
    ai_recommendation: RecommendationType | None
    ai_confidence: float | None
    accepted_ai: bool | None
    created_at: datetime
    ai_details: dict[str, Any] | None = None
    # Совпали ли детали с AI (только когда тип совпал и AI предлагал детали)
    details_match: bool | None = None


@dataclass(slots=True)
class Delivery:
    """Одна отправка уведомления: канал, адрес, номер попытки (0 — первая, 1.. — напоминания)."""

    at: datetime
    channel: NotificationChannel
    target: str  # телефон, email или «Telegram @…»
    attempt: int
    text: str = ""  # что ушло: короткое сообщение со ссылкой на сайт
    status: DeliveryStatus = DeliveryStatus.SIMULATED
    detail: str | None = None  # ошибка канала или почему имитация («не настроено»)


@dataclass(slots=True, kw_only=True)
class Notification:
    id: str
    decision_id: str
    study_id: str
    patient_id: str
    # Каналы, в которые ушло уведомление (все доступные контакты); в кабинете — всегда
    channels: tuple[NotificationChannel, ...]
    text: str  # подробный — в личном кабинете на сайте
    short_text: str = ""  # короткий со ссылкой — в SMS / email / соцсети
    status: NotificationStatus
    sent_at: datetime
    read_at: datetime | None = None
    patient_action: PatientActionType | None = None
    action_at: datetime | None = None
    appointment_id: str | None = None
    # История отправок (имитация каналов) и напоминания, пока пациент не записался
    deliveries: list[Delivery] = field(default_factory=list)
    reminders_sent: int = 0
    next_reminder_at: datetime | None = None
    # B2C: объяснение заключения пациенту простым языком {summary, terms[{term, explanation}]}
    explanation: dict[str, Any] | None = None


@dataclass(slots=True, kw_only=True)
class Appointment:
    """Запись к врачу (doctor_id) или на исследование в кабинет (research_type) — одно из двух."""

    id: str
    patient_id: str
    doctor_id: str | None
    scheduled_for: datetime
    status: AppointmentStatus
    created_at: datetime
    notification_id: str | None = None
    research_type: str | None = None
    # Какое направление из решения врача закрывает запись (rules.Requirement.key)
    requirement: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class AuditEvent:
    id: str
    actor_id: str | None
    actor_role: str | None
    action: str
    target_type: str
    target_id: str
    at: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None
