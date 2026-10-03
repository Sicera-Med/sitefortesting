from fastapi import APIRouter

from app.api.deps import DoctorUser, NotificationServiceDep, PatientUser
from app.schemas.patients import NotifyIn, PatientNotificationOut
from app.schemas.studies import NotificationOut

router = APIRouter(tags=["notifications"])


@router.post(
    "/decisions/{decision_id}/notify",
    response_model=NotificationOut,
    summary="Отправить пациенту уведомление (мок)",
)
async def notify(
    decision_id: str,
    user: DoctorUser,
    service: NotificationServiceDep,
    body: NotifyIn | None = None,
) -> NotificationOut:
    channel = body.channel if body else None
    return NotificationOut.build(service.notify(user, decision_id, channel))


@router.get(
    "/patients/me/notifications",
    response_model=list[PatientNotificationOut],
    summary="Мои уведомления (пациент)",
)
async def my_notifications(
    user: PatientUser, service: NotificationServiceDep
) -> list[PatientNotificationOut]:
    return [PatientNotificationOut.build(v) for v in service.patient_notifications(user)]


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
