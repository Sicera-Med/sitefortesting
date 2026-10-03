"""Метрики дашборда заведующего (SPEC §8). Считаются на лету по Store."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from app.domain.enums import AISource, PatientActionType, RecommendationType, StudyStatus
from app.domain.models import Decision
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
        return {
            "summary": self._summary(decisions),
            "agreement": _rate(sum(d.accepted_ai for d in with_ai), len(with_ai)),
            "agreement_by_confidence": self._by_confidence(with_ai),
            "confusion_matrix": self._confusion(with_ai),
            "latency": self._latency(),
            "by_doctor": self._by_doctor(decisions),
            "notifications": self._notifications(),
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
            "ai_failures": sum(e.action == "ai.failed" for e in self.store.audit),
        }

    def _by_confidence(self, with_ai: list[Decision]) -> dict[str, Any]:
        high = [d for d in with_ai if d.ai_confidence >= self.threshold]
        low = [d for d in with_ai if d.ai_confidence < self.threshold]
        return {
            "threshold": self.threshold,
            "high": _rate(sum(d.accepted_ai for d in high), len(high)),
            "low": _rate(sum(d.accepted_ai for d in low), len(low)),
        }

    @staticmethod
    def _confusion(with_ai: list[Decision]) -> dict[str, Any]:
        """Строки — рекомендация AI, столбцы — решение врача."""
        labels = [str(t) for t in RecommendationType]
        counts = Counter((str(d.ai_recommendation), str(d.chosen_type)) for d in with_ai)
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
        for doctor in self.store.list_doctors():
            own = [d for d in decisions if d.doctor_id == doctor.id]
            if not own:
                continue
            with_ai = [d for d in own if d.accepted_ai is not None]
            rows.append(
                {
                    "doctor_id": doctor.id,
                    "full_name": doctor.full_name,
                    "specialty": doctor.specialty,
                    "decisions": len(own),
                    **_rate(sum(d.accepted_ai for d in with_ai), len(with_ai)),
                }
            )
        return rows

    def _notifications(self) -> list[dict[str, Any]]:
        """Конверсия уведомлений по типу рекомендации врача."""
        rows = []
        for kind in RecommendationType:
            sent = [
                n
                for n in self.store.list_notifications()
                if self.store.get_decision(n.decision_id).chosen_type is kind
            ]
            actions = Counter(n.patient_action for n in sent)
            booked = actions.get(PatientActionType.BOOKED, 0)
            rows.append(
                {
                    "recommendation": str(kind),
                    "sent": len(sent),
                    "booked": booked,
                    "declined": actions.get(PatientActionType.DECLINED, 0),
                    "pending": actions.get(None, 0),
                    "booked_rate": round(booked / len(sent), 4) if sent else None,
                }
            )
        return rows

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
            "chosen_type": str(d.chosen_type),
            "accepted_ai": d.accepted_ai,
            "created_at": d.created_at.isoformat(),
        }
