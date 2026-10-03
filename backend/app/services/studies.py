from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.ai.contract import AIRequest, AIResult
from app.core.clock import utcnow
from app.core.errors import (
    AIFailedError,
    ConflictError,
    ForbiddenError,
    InvalidInputError,
    InvalidTransitionError,
    NotFoundError,
)
from app.core.ids import new_id
from app.domain import rules
from app.domain.decisions import normalize_details
from app.domain.enums import AISource, RecommendationType, Role, StudyStatus
from app.domain.models import (
    AIInference,
    Appointment,
    AuditEvent,
    Decision,
    Notification,
    Patient,
    Study,
    User,
)
from app.services import audit
from app.services.ai_service import AIService
from app.store import Store

Scope = Literal["mine", "all"]


@dataclass(slots=True)
class StudyView:
    """Study со всем, что нужно показать в списке и карточке."""

    study: Study
    patient: Patient
    doctor: User
    inference: AIInference | None
    decision: Decision | None
    notification: Notification | None
    appointment: Appointment | None
    appointment_doctor: User | None
    can_act: bool


class StudyService:
    def __init__(self, store: Store, ai: AIService) -> None:
        self.store = store
        self.ai = ai

    # --- Чтение ---

    def _get(self, user: User, study_id: str) -> Study:
        study = self.store.get_study(study_id)
        if study is None:
            raise NotFoundError("Исследование не найдено", details={"study_id": study_id})
        if not rules.can_view_study(user, study):
            raise ForbiddenError("Нет доступа к исследованию")
        return study

    def _view(self, user: User, study: Study) -> StudyView:
        decision = self.store.decision_for_study(study.id)
        notification = self.store.notification_for_decision(decision.id) if decision else None
        appointment = (
            self.store.get_appointment(notification.appointment_id)
            if notification and notification.appointment_id
            else None
        )
        return StudyView(
            study=study,
            patient=self.store.get_patient(study.patient_id),
            doctor=self.store.get_user(study.treating_doctor_id),
            inference=self.store.latest_inference(study.id),
            decision=decision,
            notification=notification,
            appointment=appointment,
            appointment_doctor=self.store.get_user(appointment.doctor_id) if appointment else None,
            can_act=rules.can_act(user, study),
        )

    def list(
        self, user: User, *, scope: Scope | None = None, statuses: list[StudyStatus] | None = None
    ) -> list[StudyView]:
        if user.role not in (Role.DOCTOR, Role.HEAD):
            raise ForbiddenError("Нет доступа к исследованиям")
        # Врач по умолчанию видит свою очередь; head всегда видит всё
        scope = scope or ("mine" if user.role is Role.DOCTOR else "all")
        doctor_id = user.id if user.role is Role.DOCTOR and scope == "mine" else None
        studies = self.store.list_studies(doctor_id=doctor_id, statuses=statuses)
        return [self._view(user, s) for s in studies]

    def card(self, user: User, study_id: str) -> StudyView:
        return self._view(user, self._get(user, study_id))

    def history(self, user: User, study_id: str) -> tuple[list[AIInference], Decision | None]:
        study = self._get(user, study_id)
        return self.store.inferences_for_study(study.id), self.store.decision_for_study(study.id)

    def timeline(self, user: User, study_id: str) -> list[tuple[AuditEvent, User | None]]:
        study = self._get(user, study_id)
        events = self.store.audit_for_target("study", study.id)
        return [(e, self.store.get_user(e.actor_id) if e.actor_id else None) for e in events]

    # --- AI ---

    def _check_can_analyze(self, user: User, study: Study) -> None:
        if not rules.can_analyze(user, study):
            raise ForbiddenError("Анализ запускает лечащий врач или заведующий")
        if study.status not in rules.ANALYZABLE_STATUSES:
            raise InvalidTransitionError(
                "После решения врача анализ не перезапускается",
                details={"status": str(study.status)},
            )

    def _save_inference(
        self, user: User, study: Study, result: AIResult, *, source: AISource, latency_ms: int
    ) -> AIInference:
        is_repeat = self.store.latest_inference(study.id) is not None
        inference = self.store.add_inference(
            AIInference(
                id=new_id("ai"),
                study_id=study.id,
                source=source,
                request_id=result.request_id,
                model_name=result.model_name,
                model_version=result.model_version,
                recommendation=result.recommendation,
                confidence=result.confidence,
                ranked_options=result.ranked_options,
                reasons=result.reasons,
                latency_ms=latency_ms,
                created_at=utcnow(),
            )
        )
        study.status = StudyStatus.AI_READY
        audit.record(
            self.store,
            user,
            "ai.reanalyzed" if is_repeat else "ai.analyzed",
            target_id=study.id,
            inference_id=inference.id,
            source=str(source),
            model=f"{inference.model_name}:{inference.model_version}",
            recommendation=str(inference.recommendation),
            confidence=inference.confidence,
            warnings=list(result.warnings),
        )
        return inference

    async def analyze(self, user: User, study_id: str) -> AIInference:
        study = self._get(user, study_id)
        self._check_can_analyze(user, study)
        patient = self.store.get_patient(study.patient_id)
        request: AIRequest = self.ai.request_for_study(study, patient)
        try:
            result, latency_ms = await self.ai.run(request)
        except AIFailedError as exc:
            # Был успешный результат раньше — остаёмся в ai_ready, иначе ai_failed
            if self.store.latest_inference(study.id) is None:
                study.status = StudyStatus.AI_FAILED
            audit.record(
                self.store,
                user,
                "ai.failed",
                target_id=study.id,
                request_id=request.request_id,
                error=exc.message,
                **exc.details,
            )
            raise
        return self._save_inference(
            user, study, result, source=self.ai.provider.source, latency_ms=latency_ms
        )

    def upload_ai_result(self, user: User, study_id: str, data: Any) -> AIInference:
        study = self._get(user, study_id)
        self._check_can_analyze(user, study)
        result = self.ai.parse_manual(data)
        return self._save_inference(user, study, result, source=AISource.MANUAL, latency_ms=0)

    # --- Решение ---

    def decide(
        self,
        user: User,
        study_id: str,
        *,
        chosen_type: RecommendationType,
        details: dict[str, Any],
        comment: str | None,
    ) -> Decision:
        study = self._get(user, study_id)
        if not rules.can_decide(user, study):
            raise ForbiddenError("Решение принимает только лечащий врач")
        if self.store.decision_for_study(study.id) is not None:
            raise ConflictError("Решение по исследованию уже принято")
        if not rules.can_transition(study.status, StudyStatus.DECIDED):
            raise InvalidTransitionError(
                "Сначала нужен результат AI (или его ошибка)",
                details={"status": str(study.status)},
            )
        try:
            clean_details = normalize_details(chosen_type, details)
        except ValueError as exc:
            raise InvalidInputError(str(exc), details={"field": "details"}) from exc

        inference = self.store.latest_inference(study.id)
        ai_rec = inference.recommendation if inference else None
        decision = self.store.add_decision(
            Decision(
                id=new_id("dc"),
                study_id=study.id,
                doctor_id=user.id,
                chosen_type=chosen_type,
                details=clean_details,
                comment=(comment or "").strip() or None,
                ai_inference_id=inference.id if inference else None,
                ai_recommendation=ai_rec,
                ai_confidence=inference.confidence if inference else None,
                accepted_ai=rules.compute_accepted_ai(chosen_type, ai_rec),
                created_at=utcnow(),
            )
        )
        study.status = StudyStatus.DECIDED
        audit.record(
            self.store,
            user,
            "decision.created",
            target_id=study.id,
            decision_id=decision.id,
            chosen_type=str(chosen_type),
            accepted_ai=decision.accepted_ai,
        )
        return decision
