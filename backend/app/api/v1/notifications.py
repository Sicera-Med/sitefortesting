from fastapi import APIRouter

from app.api.deps import (
    DoctorUser,
    NotificationServiceDep,
    PatientUser,
    SettingsDep,
    StudyServiceDep,
)
from app.schemas.patients import ExplanationOut, PatientNotificationOut, PatientStudyOut
from app.schemas.studies import NotificationOut

router = APIRouter(tags=["notifications"])


@router.get(
    "/patients/me/notifications",
    response_model=list[PatientNotificationOut],
    summary="Мои уведомления (пациент)",
)
async def my_notifications(
    user: PatientUser, service: NotificationServiceDep
) -> list[PatientNotificationOut]:
    return [PatientNotificationOut.build(v) for v in service.patient_notifications(user)]


@router.get(
    "/patients/me/studies",
    response_model=list[PatientStudyOut],
    summary="Мои исследования (пациент): статус и решение врача, без протокола",
)
async def my_studies(user: PatientUser, service: NotificationServiceDep) -> list[PatientStudyOut]:
    return [PatientStudyOut.build(v) for v in service.patient_studies(user)]


@router.post(
    "/notifications/{notification_id}/read",
    response_model=PatientNotificationOut,
    summary="Отметить уведомление прочитанным",
)
async def mark_read(
    notification_id: str, user: PatientUser, service: NotificationServiceDep
) -> PatientNotificationOut:
    return PatientNotificationOut.build(service.mark_read(user, notification_id))


@router.post(
    "/notifications/{notification_id}/decline",
    response_model=PatientNotificationOut,
    summary="Отказаться от рекомендации",
)
async def decline(
    notification_id: str, user: PatientUser, service: NotificationServiceDep
) -> PatientNotificationOut:
    return PatientNotificationOut.build(service.decline(user, notification_id))


@router.post(
    "/notifications/{notification_id}/explain",
    response_model=ExplanationOut,
    summary="Объяснение заключения простым языком (B2C AI-команды)",
)
async def explain(
    notification_id: str, user: PatientUser, service: StudyServiceDep
) -> ExplanationOut:
    return ExplanationOut.model_validate(await service.explain_for_patient(user, notification_id))


@router.post(
    "/notifications/{notification_id}/remind",
    response_model=NotificationOut,
    summary="Напомнить пациенту сейчас (лечащий врач / главврач)",
)
async def remind(
    notification_id: str,
    user: DoctorUser,
    service: NotificationServiceDep,
    settings: SettingsDep,
) -> NotificationOut:
    n = service.remind(user, notification_id, cooldown_s=settings.NOTIFY_REMIND_COOLDOWN_S)
    return NotificationOut.build(n)
