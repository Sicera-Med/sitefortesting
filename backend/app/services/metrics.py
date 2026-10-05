"""Метрики дашборда заведующего (SPEC §8). Считаются на лету по Store."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from app.domain import rules
from app.domain.decisions import EXCLUSIVE_TYPES
from app.domain.enums import AISource, PatientActionType, RecommendationType, StudyStatus
from app.domain.models import Decision, Notification
from app.store import Store


def _rate(agreed: int, total: int) -> dict[str, Any]:
    return {"agreed": agreed, "total": total, "rate": round(agreed / total, 4) if total else None}


def _p95(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]  # nearest-rank


class MetricsService:
    def __init__(self, store: Store, *, high_confidence: float) -> None:
        self.store = store
        self.threshold = high_confidence

    def dashboard(self) -> dict[str, Any]:
        decisions = self.store.list_decisions()  # новые сверху
        with_ai = [d for d in decisions if d.accepted_ai is not None]
        compared = [d for d in decisions if d.details_match is not None]
        return {
            "summary": self._summary(decisions),
            "agreement": _rate(sum(d.accepted_ai for d in with_ai), len(with_ai)),
            "agreement_by_confidence": self._by_confidence(with_ai),
            # Детали (специалист / исследования) — среди решений, где тип совпал с AI
            "details_agreement": _rate(sum(d.details_match for d in compared), len(compared)),
            "confusion_matrix": self._confusion(with_ai),
            "latency": self._latency(),
            "by_doctor": self._by_doctor(decisions),
            "notifications": self._notifications(),
            "funnel": self._funnel(),
            "recent_decisions": [self._decision_row(d) for d in decisions[:10]],
        }

    def _summary(self, decisions: list[Decision]) -> dict[str, Any]:
        by_status = Counter(s.status for s in self.store.studies.values())
        return {
            "studies_total": len(self.store.studies),
            "studies_by_status": {str(s): by_status.get(s, 0) for s in StudyStatus},
            "decisions_total": len(decisions),
            "decisions_without_ai": sum(d.accepted_ai is None for d in decisions),
            "ai_runs": len(self.store.inferences),
            "ai_failures": self.store.audit_count("ai.failed"),
        }

    def _by_confidence(self, with_ai: list[Decision]) -> dict[str, Any]:
        # Только решения, где модель сообщила уверенность (модель коллег её не даёт)
        scored = [d for d in with_ai if d.ai_confidence is not None]
        high = [d for d in scored if d.ai_confidence >= self.threshold]
        low = [d for d in scored if d.ai_confidence < self.threshold]
        return {
            "threshold": self.threshold,
            "high": _rate(sum(d.accepted_ai for d in high), len(high)),
            "low": _rate(sum(d.accepted_ai for d in low), len(low)),
        }

    @staticmethod
    def _confusion(with_ai: list[Decision]) -> dict[str, Any]:
        """Строки — рекомендация AI, столбцы — что выбрал врач.

        Врач может выбрать несколько вариантов — решение попадает в каждый выбранный столбец.
        """
        labels = [str(t) for t in RecommendationType]
        counts = Counter(
            (str(d.ai_recommendation), str(t)) for d in with_ai for t in d.chosen_types
        )
        return {
            "labels": labels,
            "matrix": [[counts.get((ai, doc), 0) for doc in labels] for ai in labels],
        }

    def _latency(self) -> dict[str, Any]:
        # Ручные загрузки (manual) не отражают скорость модели
        values = [
            i.latency_ms for i in self.store.list_inferences() if i.source is not AISource.MANUAL
        ]
        return {
            "count": len(values),
            "avg_ms": round(sum(values) / len(values)) if values else None,
            "p95_ms": _p95(values),
        }

    def _by_doctor(self, decisions: list[Decision]) -> list[dict[str, Any]]:
        rows = []
        # Врачи и все, кто ещё принимал решения (главврач)
        authors = self.store.list_doctors()
        for d in decisions:
            user = self.store.get_user(d.doctor_id)
            if user not in authors:
                authors.append(user)
        # Все врачи — и без решений (в «Показать всех»); главврач — только если решал
        for doctor in authors:
            own = [d for d in decisions if d.doctor_id == doctor.id]
            with_ai = [d for d in own if d.accepted_ai is not None]
            compared = [d for d in own if d.details_match is not None]
            details = _rate(sum(d.details_match for d in compared), len(compared))
            rows.append(
                {
                    "doctor_id": doctor.id,
                    "full_name": doctor.full_name,
                    "specialty": doctor.specialty,
                    "decisions": len(own),
                    **_rate(sum(d.accepted_ai for d in with_ai), len(with_ai)),
                    # Полное совпадение: тип и детали (специалист / исследования) как у AI
                    "details_agreed": details["agreed"],
                    "details_total": details["total"],
                    "details_rate": details["rate"],
                }
            )
        # Лидеры по согласию сверху; без решений с AI — в конце, по числу решений
        return sorted(rows, key=lambda r: (r["rate"] is None, -(r["rate"] or 0), -r["decisions"]))

    def _notifications(self) -> list[dict[str, Any]]:
        """Конверсия уведомлений по типу рекомендации врача."""
        rows = []
        # Только направления, по которым пациент записывается
        for kind in (t for t in RecommendationType if t not in EXCLUSIVE_TYPES):
            sent = [
                n
                for n in self.store.list_notifications()
                if kind in self.store.get_decision(n.decision_id).chosen_types
            ]
            # Записался = закрыл записью все направления решения; частично — ещё ждём
            booked = sum(self._fully_booked(n) for n in sent)
            declined = sum(n.patient_action is PatientActionType.DECLINED for n in sent)
            rows.append(
                {
                    "recommendation": str(kind),
                    "sent": len(sent),
                    "booked": booked,
                    "declined": declined,
                    "pending": len(sent) - booked - declined,
                    "booked_rate": round(booked / len(sent), 4) if sent else None,
                }
            )
        return rows

    def _funnel(self) -> list[dict[str, Any]]:
        """Воронка после уведомления: всего и по каждому типу направления.

        Только уведомления, по которым есть куда записываться («патологии не выявлено» — нет).
        """
        bookable = [
            (n, self.store.get_decision(n.decision_id))
            for n in self.store.list_notifications()
            if rules.needs_booking(self.store.get_decision(n.decision_id))
        ]
        groups: list[tuple[str, list[tuple[Notification, Decision]]]] = [("all", bookable)]
        for kind in RecommendationType:
            if kind in EXCLUSIVE_TYPES:  # без записи — в воронке им нечего делать
                continue
            groups.append((str(kind), [(n, d) for n, d in bookable if kind in d.chosen_types]))
        rows = []
        for scope, items in groups:
            covered = [
                rules.covered_keys(self.store.list_appointments(notification_id=n.id))
                for n, _ in items
            ]
            rows.append(
                {
                    "scope": scope,
                    "sent": len(items),
                    "read": sum(n.read_at is not None for n, _ in items),
                    "booked_any": sum(bool(c) for c in covered),
                    "booked_all": sum(
                        all(r.key in c for r in rules.required_bookings(d))
                        for (_, d), c in zip(items, covered, strict=True)
                    ),
                    "declined": sum(
                        n.patient_action is PatientActionType.DECLINED for n, _ in items
                    ),
                }
            )
        return rows

    def _fully_booked(self, n: Notification) -> bool:
        if n.patient_action is not PatientActionType.BOOKED:
            return False
        decision = self.store.get_decision(n.decision_id)
        return rules.all_covered(decision, self.store.list_appointments(notification_id=n.id))

    def _decision_row(self, d: Decision) -> dict[str, Any]:
        study = self.store.get_study(d.study_id)
        patient = self.store.get_patient(study.patient_id)
        doctor = self.store.get_user(d.doctor_id)
        return {
            "decision_id": d.id,
            "study_id": study.id,
            "study_type": str(study.study_type),
            "patient_name": patient.full_name,
            "doctor_name": doctor.full_name,
            "ai_recommendation": str(d.ai_recommendation) if d.ai_recommendation else None,
            "ai_confidence": d.ai_confidence,
            "chosen_types": [str(t) for t in d.chosen_types],
            "accepted_ai": d.accepted_ai,
            "details_match": d.details_match,
            "created_at": d.created_at.isoformat(),
        }
