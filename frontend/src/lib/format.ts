"use client";

// Подписи, даты, проценты. Справочники с backend — через useLabels().

import { useMemo } from "react";

import { useDictionaries } from "./api/hooks";
import type {
  DoctorBrief,
  Requirement,
  Dictionaries,
  NotificationChannel,
  RecommendationDetails,
  RecommendationType,
  StudyStatus,
} from "./api/types";

export const STATUS_LABELS: Record<StudyStatus, string> = {
  new: "AI анализирует",
  ai_ready: "AI готов",
  ai_failed: "AI не отвечает",
  decided: "Решение принято",
  notified: "Пациент уведомлён",
  completed: "Завершено",
};

export const RECOMMENDATION_LABELS: Record<RecommendationType, string> = {
  repeat_appointment: "Повторный приём",
  specialist_consult: "Консультация специалиста",
  additional_research: "Дополнительное исследование",
};

export const RECOMMENDATION_TYPES = Object.keys(RECOMMENDATION_LABELS) as RecommendationType[];

export const CHANNEL_LABELS: Record<NotificationChannel, string> = {
  sms: "SMS",
  email: "Email",
  social: "Соцсеть",
};

/** «SMS, Email» — каналы, куда ушло уведомление. */
export function channelsText(channels: NotificationChannel[]): string {
  return channels.map((c) => CHANNEL_LABELS[c]).join(", ") || "только личный кабинет";
}

export const ROLE_LABELS = {
  chief: "Главный врач",
  manager: "Менеджер",
  doctor: "Врач",
  patient: "Пациент",
} as const;

type DictKey = keyof Dictionaries;

/** label(dict, code) → русская подпись или сам код, пока справочники не загружены. */
export function useLabels() {
  const { data } = useDictionaries();
  return useMemo(() => {
    const maps = {} as Record<DictKey, Map<string, string>>;
    for (const key of Object.keys(data ?? {}) as DictKey[]) {
      maps[key] = new Map(data![key].map((i) => [i.code, i.label]));
    }
    return (dict: DictKey, code: string | null | undefined) =>
      code ? (maps[dict]?.get(code) ?? code) : "—";
  }, [data]);
}

export function pct(v: number | null | undefined, digits = 0): string {
  return v == null ? "—" : `${(v * 100).toFixed(digits)}%`;
}

const TZ = "Europe/Moscow"; // часовой пояс клиники (CLINIC_TZ)

export function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("ru-RU", { timeZone: TZ });
}

export function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", {
    timeZone: TZ,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("ru-RU", {
    timeZone: TZ,
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** «пн, 05.10» для заголовков дней со слотами (date — YYYY-MM-DD). */
export function fmtDay(date: string): string {
  return new Date(`${date}T12:00:00Z`).toLocaleDateString("ru-RU", {
    timeZone: TZ,
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
  });
}

/** Детали одного направления: «Онколог, Уролог» или «КТ, Биопсия» (SPEC §5.5). */
export function useDetailsText() {
  const label = useLabels();
  return (type: RecommendationType, details: RecommendationDetails): string | null => {
    if (type === "specialist_consult" && details.specialists?.length)
      return details.specialists.map((s) => label("specialists", s)).join(", ");
    if (type === "additional_research" && details.research_types?.length)
      return details.research_types.map((r) => label("research_types", r)).join(", ");
    return null;
  };
}

/** Все направления решения: [{type, label, text}] — для списков в карточке и у пациента. */
export function useDecisionItems() {
  const detailsText = useDetailsText();
  return (types: RecommendationType[], details: RecommendationDetails) =>
    RECOMMENDATION_TYPES.filter((t) => types.includes(t)).map((t) => ({
      type: t,
      label: RECOMMENDATION_LABELS[t],
      text: detailsText(t, details),
    }));
}

/** Подпись направления из решения врача: «Повторный приём», «Консультация: Кардиолог», «КТ». */
export function useRequirementLabel() {
  const label = useLabels();
  return (r: Pick<Requirement, "kind" | "code">): string =>
    r.kind === "treating"
      ? "Повторный приём у лечащего врача"
      : r.kind === "specialist"
        ? `Консультация: ${label("specialists", r.code)}`
        : label("research_types", r.code);
}

/** Куда запись: врач со специальностью или исследование. */
export function useAppointmentTarget() {
  const label = useLabels();
  return (a: { doctor: DoctorBrief | null; research_type: string | null }): string =>
    a.doctor
      ? `${a.doctor.full_name} (${label("specialists", a.doctor.specialty)})`
      : label("research_types", a.research_type);
}
