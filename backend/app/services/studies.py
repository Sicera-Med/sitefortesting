from __future__ import annotations

from dataclasses import dataclass, field
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
from app.domain.decisions import normalize_chosen, normalize_details
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
from app.services.notifications import NotificationService, RequirementView, requirement_views
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
    appointments: list[tuple[Appointment, User | None]]  # записи пациента по уведомлению
    can_act: bool
    requirements: list[RequirementView] = field(default_factory=list)


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
        raw = self.store.list_appointments(notification_id=notification.id) if notification else []
        appointments = [(a, self.store.get_user(a.doctor_id) if a.doctor_id else None) for a in raw]
        doctor = self.store.get_user(study.treating_doctor_id)
        requirements = (
            requirement_views(self.store, decision, raw, doctor)
            if notification and decision
            else []
        )
        return StudyView(
            study=study,
            patient=self.store.get_patient(study.patient_id),
            doctor=doctor,
            inference=self.store.latest_inference(study.id),
            decision=decision,
            notification=notification,
            appointments=appointments,
            can_act=rules.can_act(user, study),
            requirements=requirements,
        )

    def list(
        self, user: User, *, scope: Scope | None = None, statuses: list[StudyStatus] | None = None
    ) -> list[StudyView]:
        if user.role not in rules.STAFF_ROLES:
            raise ForbiddenError("Нет доступа к исследованиям")
        # Врач по умолчанию видит свою очередь; главврач и менеджер — всё
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
    # Анализ запускается автоматически (services/auto_analyze.py), врач его не вызывает.

    def _save_inference(
        self,
        actor: User | None,
        study: Study,
        result: AIResult,
        *,
        source: AISource,
        latency_ms: int,
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
                details=dict(result.details),
            )
        )
        # Пока шёл запрос, врач мог уже решить без AI — статус тогда не трогаем
        if study.status in rules.ANALYZABLE_STATUSES:
            study.status = StudyStatus.AI_READY
        audit.record(
            self.store,
            actor,
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

    async def analyze_auto(self, study_id: str) -> AIInference:
        """Анализ от имени системы. Бросает AIFailedError, если AI не ответил."""
        study = self.store.get_study(study_id)
        if study is None:
            raise NotFoundError("Исследование не найдено", details={"study_id": study_id})
        patient = self.store.get_patient(study.patient_id)
        request: AIRequest = self.ai.request_for_study(study, patient)
        try:
            result, latency_ms = await self.ai.run(request)
        except AIFailedError as exc:
            # В аудит — только начало серии сбоев; повторы раз в AI_RETRY_S не засоряют таймлайн
            first_failure = study.status is not StudyStatus.AI_FAILED
            if study.status is StudyStatus.NEW:
                study.status = StudyStatus.AI_FAILED
            if not first_failure:
                raise
            audit.record(
                self.store,
                None,
                "ai.failed",
                target_id=study.id,
                request_id=request.request_id,
                error=exc.message,
                **exc.details,
            )
            raise
        return self._save_inference(
            None, study, result, source=self.ai.provider.source, latency_ms=latency_ms
        )

    def upload_ai_result(self, user: User, study_id: str, data: Any) -> AIInference:
        """Запасной путь (§6.5): ответ AI в формате контракта, загруженный вручную."""
        study = self._get(user, study_id)
        if not rules.can_analyze(user, study):
            raise ForbiddenError("Загрузить ответ AI может лечащий врач или заведующий")
        if study.status not in rules.ANALYZABLE_STATUSES:
            raise InvalidTransitionError(
                "После решения врача результат AI не меняется",
                details={"status": str(study.status)},
            )
        result = self.ai.parse_manual(data)
        return self._save_inference(user, study, result, source=AISource.MANUAL, latency_ms=0)

    # --- Лечащий врач ---

    def reassign(self, user: User, study_id: str, doctor_id: str) -> StudyView:
        """Главврач передаёт пациента другому врачу — пока решение не принято."""
        study = self._get(user, study_id)
        if user.role is not Role.CHIEF:
            raise ForbiddenError("Сменить лечащего врача может только главврач")
        if study.status not in rules.DECIDABLE_STATUSES:
            raise InvalidTransitionError(
                "Решение уже принято — лечащего врача не сменить",
                details={"status": str(study.status)},
            )
        doctor = self.store.get_user(doctor_id)
        if doctor is None or doctor.role is not Role.DOCTOR or not doctor.active:
            raise NotFoundError("Врач не найден", details={"doctor_id": doctor_id})
        if doctor.id != study.treating_doctor_id:
            previous = study.treating_doctor_id
            study.treating_doctor_id = doctor.id
            audit.record(
                self.store,
                user,
                "study.reassigned",
                target_id=study.id,
                from_doctor_id=previous,
                to_doctor_id=doctor.id,
            )
        return self._view(user, study)

    # --- Решение ---

    def decide(
        self,
        user: User,
        study_id: str,
        *,
        chosen_types: list[RecommendationType],
        details: dict[str, Any],
        comment: str | None,
    ) -> Decision:
        study = self._get(user, study_id)
        if not rules.can_decide(user, study):
            raise ForbiddenError("Решение принимает лечащий врач или главврач")
        if self.store.decision_for_study(study.id) is not None:
            raise ConflictError("Решение по исследованию уже принято")
        if not rules.can_transition(study.status, StudyStatus.DECIDED):
            raise InvalidTransitionError(
                "Решение по исследованию уже принято", details={"status": str(study.status)}
            )
        try:
            chosen = normalize_chosen(chosen_types)
            clean_details = normalize_details(chosen, details)
        except ValueError as exc:
            raise InvalidInputError(str(exc), details={"field": "details"}) from exc

        # Решение без AI тоже допустимо: тогда снапшот AI пустой
        inference = self.store.latest_inference(study.id)
        ai_rec = inference.recommendation if inference else None
        decision = self.store.add_decision(
            Decision(
                id=new_id("dc"),
                study_id=study.id,
                doctor_id=user.id,
                chosen_types=chosen,
                details=clean_details,
                comment=(comment or "").strip() or None,
                ai_inference_id=inference.id if inference else None,
                ai_recommendation=ai_rec,
                ai_confidence=inference.confidence if inference else None,
                accepted_ai=rules.compute_accepted_ai(chosen, ai_rec),
                created_at=utcnow(),
                ai_details=dict(inference.details) if inference else None,
                details_match=rules.compute_details_match(
                    chosen, clean_details, ai_rec, inference.details if inference else None
                ),
            )
        )
        study.status = StudyStatus.DECIDED
        audit.record(
            self.store,
            user,
            "decision.created",
            target_id=study.id,
            decision_id=decision.id,
            chosen_types=[str(t) for t in chosen],
            accepted_ai=decision.accepted_ai,
        )
        # Пациент узнаёт о решении сразу — во все доступные каналы
        NotificationService(self.store).notify(user, decision)
        return decision
