"use client";

// Хуки TanStack Query поверх api(). Ключи: ["studies", ...], ["study", id], ...

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type {
  Account,
  AccountPatch,
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
  Notification,
  PatientNotification,
  PatientStudy,
  StaffDoctor,
  StaffDoctorIn,
  StaffDoctorPatch,
  PatientBrief,
  StudyCard,
  StudyIn,
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

export function usePatients() {
  return useQuery({
    queryKey: ["patients"],
    queryFn: () => api<PatientBrief[]>("/studies/patients"),
    staleTime: 60_000,
  });
}

export function useCreateStudy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: StudyIn) => api<StudyCard>("/studies", { method: "POST", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["studies"] }),
  });
}

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
    // Ждём AI или отправку SMS / email из очереди — опрашиваем
    refetchInterval: (q) => {
      const d = q.state.data;
      if (!d) return false;
      const sending = d.notification?.deliveries.some((x) => x.status === "pending");
      return AI_PENDING.includes(d.status) || sending ? POLL_MS : false;
    },
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

/** Одно исследование — в AI не чаще раза в 10 с (как AI_SEND_COOLDOWN_S на backend). */
export const AI_SEND_COOLDOWN_MS = 10_000;
// Время последней отправки по исследованию — на всю вкладку, переживает повторное открытие карточки
const aiLastSend = new Map<string, number>();

/** Сколько ещё ждать до следующей отправки, мс (0 — можно). */
export function aiSendWait(id: string, now: number): number {
  const last = aiLastSend.get(id);
  return last == null ? 0 : Math.max(0, last + AI_SEND_COOLDOWN_MS - now);
}

/** Отправка в AI (автоматически при открытии карточки или кнопкой). */
export function useRetryAI(id: string) {
  const invalidate = useInvalidateStudy(id);
  return useMutation({
    mutationFn: () => {
      // Двойной клик или повторное открытие карточки — второй запрос даже не уходит на backend
      const wait = aiSendWait(id, Date.now());
      if (wait > 0) {
        throw new Error(`Повторно отправить можно через ${Math.ceil(wait / 1000)} с`);
      }
      aiLastSend.set(id, Date.now());
      return api<Inference>(`/studies/${id}/analyze`, { method: "POST" });
    },
    // и при сбое: в карточке и таймлайне — новая ошибка
    onSettled: invalidate,
  });
}

/** «Напомнить сейчас»: следующее напоминание пациенту сразу (лечащий врач / главврач). */
export function useRemind(studyId: string) {
  const invalidate = useInvalidateStudy(studyId);
  return useMutation({
    mutationFn: (notificationId: string) =>
      api<Notification>(`/notifications/${notificationId}/remind`, { method: "POST" }),
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

export function useReassign(id: string) {
  const invalidate = useInvalidateStudy(id);
  return useMutation({
    mutationFn: (doctorId: string) =>
      api<StudyCard>(`/studies/${id}/reassign`, { method: "POST", body: { doctor_id: doctorId } }),
    onSuccess: invalidate,
  });
}

// --- Личный кабинет ---

export function useAccount() {
  return useQuery({ queryKey: ["account"], queryFn: () => api<Account>("/account") });
}

export function useUpdateAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AccountPatch) => api<Account>("/account", { method: "PATCH", body }),
    onSuccess: (data) => qc.setQueryData(["account"], data),
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (body: { old_password: string; new_password: string }) =>
      api<void>("/account/password", { method: "POST", body }),
  });
}

// --- Главврач: врачи ---

export function useStaffDoctors() {
  return useQuery({
    queryKey: ["staff-doctors"],
    queryFn: () => api<StaffDoctor[]>("/staff/doctors"),
  });
}

function useInvalidateStaff() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["staff-doctors"] });
    qc.invalidateQueries({ queryKey: ["doctors"] });
  };
}

export function useCreateDoctor() {
  const invalidate = useInvalidateStaff();
  return useMutation({
    mutationFn: (body: StaffDoctorIn) =>
      api<StaffDoctor>("/staff/doctors", { method: "POST", body }),
    onSuccess: invalidate,
  });
}

export function useUpdateDoctor() {
  const invalidate = useInvalidateStaff();
  return useMutation({
    mutationFn: ({ id, ...body }: StaffDoctorPatch & { id: string }) =>
      api<StaffDoctor>(`/staff/doctors/${id}`, { method: "PATCH", body }),
    onSuccess: invalidate,
  });
}

// --- Пациент ---

/** B2C: объяснение заключения простым языком — запрашивается при открытии карточки. */
export function useExplain() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: string) =>
      api<{ summary: string; terms: { term: string; explanation: string }[] }>(
        `/notifications/${notificationId}/explain`,
        { method: "POST" },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["my-notifications"] }),
  });
}

export function useMyStudies() {
  return useQuery({
    queryKey: ["my-studies"],
    queryFn: () => api<PatientStudy[]>("/patients/me/studies"),
  });
}

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
    qc.invalidateQueries({ queryKey: ["my-studies"] });
    qc.invalidateQueries({ queryKey: ["appointments"] });
    qc.invalidateQueries({ queryKey: ["slots"] });
    qc.invalidateQueries({ queryKey: ["research-slots"] });
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

/** Свободное время кабинета исследования (КТ, биопсия, анализы…). */
export function useResearchSlots(code: string | null, days = 7) {
  return useQuery({
    queryKey: ["research-slots", code, days],
    queryFn: () => api<DaySlots[]>(`/research/${code}/slots`, { query: { days } }),
    enabled: !!code,
  });
}

/** Записи: пациенту — свои, врачу — его расписание, главврачу — расписание врача doctorId. */
export function useAppointments(doctorId?: string | null) {
  return useQuery({
    queryKey: ["appointments", doctorId ?? null],
    queryFn: () =>
      api<Appointment[]>("/appointments", { query: { doctor_id: doctorId ?? undefined } }),
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
