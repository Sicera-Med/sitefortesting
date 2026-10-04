"""Каналы уведомлений: SMS (SMSPilot) и email (SMTP Яндекса). Соцсети — всегда имитация.

Отправка блокирующая (HTTP / SMTP) — её делает фоновая очередь services/outbox.py в потоке,
решение врача отправки не ждёт. При NOTIFY_REAL=false или без ключей — имитация, как раньше.
"""

from __future__ import annotations

import re
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

import httpx

from app.core.config import Settings
from app.domain.enums import DeliveryStatus, NotificationChannel

SMSPILOT_URL = "https://smspilot.ru/api.php"
EMAIL_SUBJECT = "Третье мнение: результат исследования"
EMAIL_FROM_NAME = "Третье мнение"


class ChannelError(Exception):
    """Канал не принял сообщение — текст ошибки увидит врач в истории отправок."""


def plan(settings: Settings, channel: NotificationChannel) -> tuple[DeliveryStatus, str | None]:
    """Отправлять по-настоящему (PENDING — в очередь) или имитировать — и почему."""
    if not settings.NOTIFY_REAL or channel is NotificationChannel.SOCIAL:
        return DeliveryStatus.SIMULATED, None
    if channel is NotificationChannel.SMS:
        if not settings.NOTIFY_SMS:
            return DeliveryStatus.SIMULATED, "канал SMS выключен"
        if not settings.SMSPILOT_API_KEY:
            return DeliveryStatus.SIMULATED, "не настроено: SMSPILOT_API_KEY"
    if channel is NotificationChannel.EMAIL:
        if not settings.NOTIFY_EMAIL:
            return DeliveryStatus.SIMULATED, "канал email выключен"
        if not (settings.SMTP_USER and settings.SMTP_PASSWORD):
            return DeliveryStatus.SIMULATED, "не настроено: SMTP_USER / SMTP_PASSWORD"
    return DeliveryStatus.PENDING, None


def normalize_phone(phone: str) -> str:
    """«+7 (900) 123-45-67» / «8900…» → «7900…» — формат SMSPilot."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    if len(digits) != 11 or digits[0] != "7":
        raise ChannelError(f"Номер не похож на российский: {phone}")
    return digits


def send_sms(settings: Settings, phone: str, text: str) -> None:
    params = {
        "send": text,
        "to": normalize_phone(phone),
        "apikey": settings.SMSPILOT_API_KEY,
        "format": "json",
    }
    if settings.SMSPILOT_FROM:
        params["from"] = settings.SMSPILOT_FROM
    try:
        r = httpx.get(SMSPILOT_URL, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ChannelError(f"SMSPilot недоступен: {exc.__class__.__name__}") from exc
    error = data.get("error") if isinstance(data, dict) else None
    if error:
        text = error.get("description_ru") or error.get("description") or str(error)
        raise ChannelError(f"SMSPilot: {text}")


def send_email(settings: Settings, to: str, text: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = EMAIL_SUBJECT
    msg["From"] = formataddr((EMAIL_FROM_NAME, settings.SMTP_USER))
    msg["To"] = to
    msg.set_content(text)
    try:
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as smtp:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise ChannelError(f"SMTP: {exc.__class__.__name__}: {str(exc)[:150]}") from exc


def send(settings: Settings, channel: NotificationChannel, target: str, text: str) -> None:
    match channel:
        case NotificationChannel.SMS:
            send_sms(settings, target, text)
        case NotificationChannel.EMAIL:
            send_email(settings, target, text)
        case _:
            raise ChannelError(f"Канал {channel} не отправляется по-настоящему")
