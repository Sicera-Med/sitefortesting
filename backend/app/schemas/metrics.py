from __future__ import annotations

from pydantic import BaseModel


class Rate(BaseModel):
    agreed: int
    total: int
    rate: float | None  # None — нет данных


class Summary(BaseModel):
    studies_total: int
    studies_by_status: dict[str, int]
    decisions_total: int
    decisions_without_ai: int
    ai_runs: int
    ai_failures: int


class AgreementByConfidence(BaseModel):
    threshold: float
    high: Rate
    low: Rate


class ConfusionMatrix(BaseModel):
    labels: list[str]
    matrix: list[list[int]]  # [ai][doctor]


class Latency(BaseModel):
    count: int
    avg_ms: int | None
    p95_ms: int | None


class DoctorRow(Rate):
    doctor_id: str
    full_name: str
    specialty: str | None
    decisions: int


class NotificationRow(BaseModel):
    recommendation: str
    sent: int
    booked: int
    declined: int
    pending: int
    booked_rate: float | None


class DecisionRow(BaseModel):
    decision_id: str
    study_id: str
    study_type: str
    patient_name: str
    doctor_name: str
    ai_recommendation: str | None
    ai_confidence: float | None
    chosen_type: str
    accepted_ai: bool | None
    created_at: str


class DashboardOut(BaseModel):
    summary: Summary
    agreement: Rate
    agreement_by_confidence: AgreementByConfidence
    confusion_matrix: ConfusionMatrix
    latency: Latency
    by_doctor: list[DoctorRow]
    notifications: list[NotificationRow]
    recent_decisions: list[DecisionRow]
