from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AppointmentServiceDep, CurrentUser
from app.core.errors import InvalidInputError
from app.domain.enums import AppointmentStatus
from app.schemas.common import DoctorBrief
from app.schemas.patients import AppointmentIn, AppointmentOut, AppointmentPatch, DaySlotsOut

router = APIRouter(tags=["appointments"])


@router.get("/doctors", response_model=list[DoctorBrief], summary="Список врачей")
async def doctors(
    user: CurrentUser,
    service: AppointmentServiceDep,
    specialty: Annotated[str | None, Query(description="Код специальности")] = None,
) -> list[DoctorBrief]:
    return [DoctorBrief.build(d) for d in service.doctors(specialty)]


@router.get(
    "/doctors/{doctor_id}/slots",
    response_model=list[DaySlotsOut],
    summary="Свободные слоты врача по дням (UTC)",
)
async def slots(
    doctor_id: str,
    user: CurrentUser,
    service: AppointmentServiceDep,
    start: Annotated[date | None, Query(description="С какой даты, по умолчанию сегодня")] = None,
    days: Annotated[int, Query(ge=1, le=14)] = 7,
) -> list[DaySlotsOut]:
    return [DaySlotsOut.build(d) for d in service.slots(doctor_id, start=start, days=days)]


@router.get(
    "/research/{code}/slots",
    response_model=list[DaySlotsOut],
    summary="Свободное время кабинета исследования по дням (UTC)",
)
async def research_slots(
    code: str,
    user: CurrentUser,
    service: AppointmentServiceDep,
    start: Annotated[date | None, Query(description="С какой даты, по умолчанию сегодня")] = None,
    days: Annotated[int, Query(ge=1, le=14)] = 7,
) -> list[DaySlotsOut]:
    return [DaySlotsOut.build(d) for d in service.research_slots(code, start=start, days=days)]


@router.get("/appointments", response_model=list[AppointmentOut], summary="Записи")
async def list_appointments(
    user: CurrentUser,
    service: AppointmentServiceDep,
    doctor_id: Annotated[
        str | None, Query(description="Расписание врача (главврачу — любого)")
    ] = None,
) -> list[AppointmentOut]:
    return [AppointmentOut.build(v) for v in service.list(user, doctor_id=doctor_id)]


@router.post(
    "/appointments", response_model=AppointmentOut, summary="Записаться к врачу или на исследование"
)
async def book(
    body: AppointmentIn, user: CurrentUser, service: AppointmentServiceDep
) -> AppointmentOut:
    view = service.book(
        user,
        doctor_id=body.doctor_id,
        research_type=body.research_type,
        scheduled_for=body.scheduled_for,
        notification_id=body.notification_id,
        requirement=body.requirement,
    )
    return AppointmentOut.build(view)


@router.patch("/appointments/{appointment_id}", response_model=AppointmentOut, summary="Отмена")
async def update_appointment(
    appointment_id: str, body: AppointmentPatch, user: CurrentUser, service: AppointmentServiceDep
) -> AppointmentOut:
    if body.status is not AppointmentStatus.CANCELLED:
        raise InvalidInputError("Поддерживается только отмена записи (status=cancelled)")
    return AppointmentOut.build(service.cancel(user, appointment_id))
