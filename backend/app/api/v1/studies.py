from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Query

from app.api.deps import ChiefUser, DoctorUser, StaffUser, StudyServiceDep
from app.core.clock import utcnow
from app.domain.enums import StudyStatus
from app.schemas.common import PatientBrief
from app.schemas.studies import (
    AuditEventOut,
    DecisionIn,
    DecisionOut,
    InferenceOut,
    ReassignIn,
    StudyCard,
    StudyHistoryOut,
    StudyIn,
    StudyListItem,
)

router = APIRouter(prefix="/studies", tags=["studies"])


@router.post("", response_model=StudyCard, summary="Новое исследование из DICOM SR")
async def create_study(body: StudyIn, user: DoctorUser, service: StudyServiceDep) -> StudyCard:
    return StudyCard.build(service.create(user, **body.model_dump()))


@router.get(
    "/patients", response_model=list[PatientBrief], summary="Пациенты (для нового исследования)"
)
async def patients(user: StaffUser, service: StudyServiceDep) -> list[PatientBrief]:
    now = utcnow()
    return [PatientBrief.build(p, now) for p in service.patients(user)]


@router.get("", response_model=list[StudyListItem], summary="Список исследований")
async def list_studies(
    user: StaffUser,
    service: StudyServiceDep,
    scope: Annotated[
        Literal["mine", "all"] | None,
        Query(description="mine — свои (по умолчанию у врача), all — все (read-only чужие)"),
    ] = None,
    status: Annotated[list[StudyStatus] | None, Query(description="Фильтр по статусам")] = None,
) -> list[StudyListItem]:
    return [StudyListItem.build(v) for v in service.list(user, scope=scope, statuses=status)]


@router.get("/{study_id}", response_model=StudyCard, summary="Карточка исследования")
async def get_study(study_id: str, user: StaffUser, service: StudyServiceDep) -> StudyCard:
    return StudyCard.build(service.card(user, study_id))


@router.post(
    "/{study_id}/ai-result",
    response_model=InferenceOut,
    summary="Загрузить ответ AI вручную (JSON по контракту §6.2)",
)
async def upload_ai_result(
    study_id: str,
    user: StaffUser,
    service: StudyServiceDep,
    data: Annotated[dict[str, Any], Body(description="Ответ модели в формате контракта")],
) -> InferenceOut:
    return InferenceOut.build(service.upload_ai_result(user, study_id, data))


@router.post("/{study_id}/decision", response_model=DecisionOut, summary="Решение врача")
async def decide(
    study_id: str, body: DecisionIn, user: DoctorUser, service: StudyServiceDep
) -> DecisionOut:
    decision = service.decide(
        user, study_id, chosen_types=body.chosen_types, details=body.details, comment=body.comment
    )
    return DecisionOut.build(decision)


@router.post(
    "/{study_id}/analyze",
    response_model=InferenceOut,
    summary="Повторно отправить в AI после сбоя (лечащий врач или главврач)",
)
async def retry_ai(study_id: str, user: DoctorUser, service: StudyServiceDep) -> InferenceOut:
    return InferenceOut.build(await service.retry_ai(user, study_id))


@router.post(
    "/{study_id}/reassign", response_model=StudyCard, summary="Сменить лечащего врача (главврач)"
)
async def reassign(
    study_id: str, body: ReassignIn, user: ChiefUser, service: StudyServiceDep
) -> StudyCard:
    return StudyCard.build(service.reassign(user, study_id, body.doctor_id))


@router.get("/{study_id}/history", response_model=StudyHistoryOut, summary="Все AI-прогоны")
async def history(study_id: str, user: StaffUser, service: StudyServiceDep) -> StudyHistoryOut:
    inferences, decision = service.history(user, study_id)
    return StudyHistoryOut(
        inferences=[InferenceOut.build(i) for i in inferences],
        decision=DecisionOut.build(decision) if decision else None,
    )


@router.get("/{study_id}/audit", response_model=list[AuditEventOut], summary="Таймлайн")
async def timeline(study_id: str, user: StaffUser, service: StudyServiceDep) -> list[AuditEventOut]:
    return [AuditEventOut.build(e, actor) for e, actor in service.timeline(user, study_id)]
