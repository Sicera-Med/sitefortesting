from enum import StrEnum


class Role(StrEnum):
    CHIEF = "chief"  # главврач: решает по любым пациентам, управляет врачами
    MANAGER = "manager"  # менеджер: только метрики
    DOCTOR = "doctor"
    PATIENT = "patient"


class Sex(StrEnum):
    M = "m"
    F = "f"


class StudyType(StrEnum):
    XRAY = "xray"
    CT = "ct"
    MRI = "mri"
    ULTRASOUND = "ultrasound"
    MAMMOGRAPHY = "mammography"


class StudyStatus(StrEnum):
    NEW = "new"
    AI_READY = "ai_ready"
    AI_FAILED = "ai_failed"
    DECIDED = "decided"
    NOTIFIED = "notified"
    COMPLETED = "completed"


class RecommendationType(StrEnum):
    REPEAT_APPOINTMENT = "repeat_appointment"
    SPECIALIST_CONSULT = "specialist_consult"
    ADDITIONAL_RESEARCH = "additional_research"
    URGENT_HOSPITALIZATION = "urgent_hospitalization"  # срочно в стационар — без записи
    NO_PATHOLOGY = "no_pathology"  # патологии не выявлено — действий не требуется


class AISource(StrEnum):
    MOCK = "mock"
    HTTP = "http"
    MANUAL = "manual"


class NotificationChannel(StrEnum):
    SMS = "sms"
    EMAIL = "email"


class DeliveryStatus(StrEnum):
    PENDING = "pending"  # в очереди на отправку (services/outbox.py)
    SENT = "sent"  # ушло через SMSPilot / SMTP
    FAILED = "failed"  # канал вернул ошибку
    SIMULATED = "simulated"  # имитация: настоящая отправка выключена или не настроена


class NotificationStatus(StrEnum):
    SENT = "sent"
    READ = "read"


class PatientActionType(StrEnum):
    BOOKED = "booked"
    DECLINED = "declined"


class AppointmentStatus(StrEnum):
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"
