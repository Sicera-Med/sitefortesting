"use client";

// Хуки TanStack Query поверх api(). Ключи: ["studies", ...], ["study", id], ...

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type {
  Appointment,
  AppointmentIn,
  AuditEvent,
  Dashboard,
  DaySlots,
  Decision,
  DecisionIn,
  DemoAccount,
  Dictionaries,
  DoctorBrief,
  Inference,
  PatientNotification,
  StudyCard,
  StudyListItem,
  StudyStatus,
} from "./types";

// --- Справочники ---

export function useDictionaries() {
  return useQuery({
    queryKey: ["dictionaries"],
    queryFn: () => api<Dictionaries>("/dictionaries"),
    staleTime: Infinity,
  });
}

export function useDemoUsers() {
  return useQuery({
    queryKey: ["demo-users"],
    queryFn: () => api<DemoAccount[]>("/auth/demo-users"),
    staleTime: Infinity,
    retry: false,
  });
}

// --- Studies ---

// Анализ идёт на сервере сам — пока есть исследования без ответа AI, опрашиваем
const AI_PENDING: StudyStatus[] = ["new", "ai_failed"];
const POLL_MS = 3000;

export function useStudies(scope: "mine" | "all", status?: StudyStatus[]) {
  return useQuery({
    queryKey: ["studies", scope, status ?? []],
    queryFn: () => api<StudyListItem[]>("/studies", { query: { scope, status } }),
    refetchInterval: (q) =>
      q.state.data?.some((s) => AI_PENDING.includes(s.status)) ? POLL_MS : false,
  });
}

export function useStudy(id: string) {
  return useQuery({
    queryKey: ["study", id],
    queryFn: () => api<StudyCard>(`/studies/${id}`),
    refetchInterval: (q) =>
      q.state.data && AI_PENDING.includes(q.state.data.status) ? POLL_MS : false,
  });
}

export function useStudyAudit(id: string) {
  return useQuery({
    queryKey: ["study", id, "audit"],
    queryFn: () => api<AuditEvent[]>(`/studies/${id}/audit`),
    refetchInterval: POLL_MS * 2,
  });
}

// После любого действия по Study обновляем карточку, очередь и дашборд.
function useInvalidateStudy(id: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["study", id] });
    qc.invalidateQueries({ queryKey: ["studies"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
  };
}

export function useUploadAIResult(id: string) {
  const invalidate = useInvalidateStudy(id);
  return useMutation({
    mutationFn: (payload: unknown) =>
      api<Inference>(`/studies/${id}/ai-result`, {
        method: "POST",
        body: payload,
      }),
    onSettled: invalidate,
  });
}

export function useDecide(id: string) {
  const invalidate = useInvalidateStudy(id);
  return useMutation({
    mutationFn: (body: DecisionIn) =>
      api<Decision>(`/studies/${id}/decision`, { method: "POST", body }),
    onSuccess: invalidate,
  });
}

// --- Пациент ---

export function useMyNotifications() {
  return useQuery({
    queryKey: ["my-notifications"],
    queryFn: () => api<PatientNotification[]>("/patients/me/notifications"),
  });
}

function useInvalidatePatient() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["my-notifications"] });
    qc.invalidateQueries({ queryKey: ["appointments"] });
    qc.invalidateQueries({ queryKey: ["slots"] });
  };
}

export function useMarkRead() {
  const invalidate = useInvalidatePatient();
  return useMutation({
    mutationFn: (id: string) =>
      api<PatientNotification>(`/notifications/${id}/read`, { method: "POST" }),
    onSuccess: invalidate,
  });
}

export function useDecline() {
  const invalidate = useInvalidatePatient();
  return useMutation({
    mutationFn: (id: string) =>
      api<PatientNotification>(`/notifications/${id}/decline`, {
        method: "POST",
      }),
    onSuccess: invalidate,
  });
}

export function useDoctors(specialty?: string) {
  return useQuery({
    queryKey: ["doctors", specialty ?? null],
    queryFn: () => api<DoctorBrief[]>("/doctors", { query: { specialty } }),
    staleTime: 5 * 60_000,
  });
}

export function useSlots(doctorId: string | null, days = 7) {
  return useQuery({
    queryKey: ["slots", doctorId, days],
    queryFn: () => api<DaySlots[]>(`/doctors/${doctorId}/slots`, { query: { days } }),
    enabled: !!doctorId,
  });
}

export function useAppointments() {
  return useQuery({
    queryKey: ["appointments"],
    queryFn: () => api<Appointment[]>("/appointments"),
  });
}

export function useBook() {
  const invalidate = useInvalidatePatient();
  return useMutation({
    mutationFn: (body: AppointmentIn) =>
      api<Appointment>("/appointments", { method: "POST", body }),
    onSuccess: invalidate,
  });
}

export function useCancelAppointment() {
  const invalidate = useInvalidatePatient();
  return useMutation({
    mutationFn: (id: string) =>
      api<Appointment>(`/appointments/${id}`, {
        method: "PATCH",
        body: { status: "cancelled" },
      }),
    onSuccess: invalidate,
  });
}

// --- Заведующий ---

export function useDashboard() {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<Dashboard>("/metrics/dashboard"),
  });
}
