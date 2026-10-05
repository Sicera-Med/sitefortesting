// Типы API — вручную по backend/app/schemas (SPEC §7). Время — ISO-строки в UTC.

export type Role = "chief" | "manager" | "doctor" | "patient";
export type Sex = "m" | "f";
export type StudyType = "xray" | "ct" | "mri" | "ultrasound" | "mammography";
export type StudyStatus = "new" | "ai_ready" | "ai_failed" | "decided" | "notified" | "completed";
// urgent_hospitalization и no_pathology — только отдельно, без записи
export type RecommendationType =
  | "repeat_appointment"
  | "specialist_consult"
  | "additional_research"
  | "urgent_hospitalization"
  | "no_pathology";
export type AISource = "mock" | "http" | "manual";
export type NotificationChannel = "sms" | "email";
export type NotificationStatus = "sent" | "read";
export type PatientActionType = "booked" | "declined";
export type AppointmentStatus = "scheduled" | "cancelled";

export interface ApiErrorBody {
  error: { code: string; message: string; details?: unknown };
}

// --- Auth ---

export interface User {
  id: string;
  role: Role;
  email: string;
  full_name: string;
  specialty: string | null;
  patient_id: string | null;
}

export interface TokenOut {
  access_token: string;
  token_type: string;
  user: User;
}

export interface DemoAccount {
  email: string;
  password: string;
  full_name: string;
  role: Role;
  specialty: string | null;
}

// --- Общее ---

export interface DoctorBrief {
  id: string;
  full_name: string;
  specialty: string | null;
}

export interface PatientBrief {
  id: string;
  full_name: string;
  birth_date: string;
  age: number;
  sex: Sex;
}

export interface DictItem {
  code: string;
  label: string;
}

export interface Dictionaries {
  recommendation_types: DictItem[];
  study_types: DictItem[];
  body_regions: DictItem[];
  specialists: DictItem[];
  research_types: DictItem[];
}

// --- AI ---

export interface RankedOption {
  type: RecommendationType;
  score: number | null; // null — модель дала только порядок вариантов
}

export interface Reason {
  code: string;
  label: string;
  weight: number | null; // null — порядок причин = важность
}

/** Детали, которые предлагает AI или выбирает врач (SPEC §5.5, §6.2). */
export interface RecommendationDetails {
  specialists?: string[];
  research_types?: string[];
}

/** Документ, на котором основан пункт: КР Минздрава, методичка НПКЦ ДиТ и т. п. */
export interface SourceRef {
  text: string; // «КР «…» (Минздрав, 2025), стр. 89»
  document: string | null;
  organization: string | null;
  year: string | number | null;
  pages: string | null;
  url: string | null; // официальная страница (PDF — сразу на нужной странице)
}

export interface AIItem {
  code: string;
  reason: string | null;
  timing: string | null;
  source_refs: SourceRef[];
  unconfirmed_sources: string[]; // модель сослалась, но в документе такого действия нет
}

export interface AIOption {
  type: RecommendationType;
  recommended: boolean;
  rationale: string | null;
  items: AIItem[];
  source_refs: SourceRef[];
  unconfirmed_sources: string[];
}

export interface Inference {
  id: string;
  source: AISource;
  request_id: string;
  model_name: string;
  model_version: string;
  recommendation: RecommendationType;
  confidence: number | null; // модель коллег уверенность не сообщает
  ranked_options: RankedOption[];
  reasons: Reason[];
  details: RecommendationDetails;
  options: AIOption[]; // все варианты модели, основной первым ([] — старый формат)
  guidelines_mode: string | null; // справочник: по словам протокола / весь
  latency_ms: number;
  created_at: string;
}

// --- Решение ---

/** specialists — для консультации, research_types — для обследования; повторный приём без деталей. */
export type DecisionDetails = RecommendationDetails;

export interface DecisionIn {
  chosen_types: RecommendationType[]; // от одного до трёх
  details: DecisionDetails;
  comment?: string | null;
}

export interface Decision {
  id: string;
  study_id: string;
  doctor_id: string;
  chosen_types: RecommendationType[];
  details: RecommendationDetails;
  comment: string | null;
  ai_inference_id: string | null;
  ai_recommendation: RecommendationType | null;
  ai_confidence: number | null;
  accepted_ai: boolean | null;
  ai_details: RecommendationDetails | null;
  details_match: boolean | null;
  created_at: string;
}

// --- Уведомления ---

export interface Notification {
  id: string;
  decision_id: string;
  channels: NotificationChannel[]; // все доступные контакты пациента
  text: string; // подробный — на сайте
  short_text: string; // короткий со ссылкой — в email (SMS — ещё короче)
  status: NotificationStatus;
  sent_at: string;
  read_at: string | null;
  patient_action: PatientActionType | null;
  action_at: string | null;
  appointment_id: string | null;
  // История отправок и напоминания: раз в неделю, до max_reminders раз
  deliveries: Delivery[];
  reminders_sent: number;
  max_reminders: number;
  next_reminder_at: string | null;
}

export interface Delivery {
  at: string;
  channel: NotificationChannel;
  target: string; // телефон или email
  attempt: number; // 0 — первое уведомление, 1.. — напоминания
  text: string; // что ушло в канал
  status: DeliveryStatus;
  detail: string | null; // ошибка канала или почему имитация
}

/** pending — в очереди, sent — ушло через SMSPilot / SMTP, simulated — имитация. */
export type DeliveryStatus = "pending" | "sent" | "failed" | "simulated";

/** Исследование в кабинете пациента: статус и решение врача, без текста протокола. */
export interface PatientStudy {
  id: string;
  study_type: StudyType;
  body_region: string;
  performed_at: string;
  treating_doctor: DoctorBrief;
  recommendations: RecommendationType[] | null; // null — врач ещё не решил
  notification_id: string | null;
  patient_action: PatientActionType | null;
  booking: BookingProgress | null;
}

// --- Study ---

export interface StudyListItem {
  id: string;
  status: StudyStatus;
  study_type: StudyType;
  body_region: string;
  performed_at: string;
  patient: PatientBrief;
  doctor: DoctorBrief;
  ai: { recommendation: RecommendationType; confidence: number | null } | null;
  decision: { chosen_types: RecommendationType[]; accepted_ai: boolean | null } | null;
  booking: BookingProgress | null; // сколько направлений пациент закрыл записью
  ai_auto: boolean; // автоотправка в AI включена; false — врач отправляет кнопкой
  can_act: boolean;
}

export interface CardAppointment {
  id: string;
  doctor: DoctorBrief | null; // null — запись на исследование
  research_type: string | null;
  requirement: string | null;
  scheduled_for: string;
  status: AppointmentStatus;
}

export type RequirementKind = "treating" | "specialist" | "research";

/** Направление из решения врача; кейс закрыт, когда записи есть по всем. */
export interface Requirement {
  key: string; // "treating" | "specialist:<код>" | "research:<код>"
  kind: RequirementKind;
  code: string | null;
  doctor: DoctorBrief | null; // врач записи; для повторного приёма — лечащий врач
  appointment_id: string | null;
  scheduled_for: string | null;
}

export interface BookingProgress {
  booked: number;
  required: number;
}

/** Автоповтор после сбоя AI: раз в AI_RETRY_S (8 ч), не больше AI_MAX_AUTO_ATTEMPTS (3). */
export interface AIRetry {
  failures: number; // неудачных автоматических попыток подряд
  next_at: string | null; // следующая автоматическая попытка
  stopped: boolean; // автоповтор остановлен — только ручная отправка
}

export interface StudyIn {
  patient_id: string;
  study_type: StudyType;
  body_region: string;
  description: string; // описание из протокола: строки «Поле- значение»
  treating_doctor_id?: string | null;
}

export interface StudyCard {
  id: string;
  status: StudyStatus;
  study_type: StudyType;
  body_region: string;
  performed_at: string;
  created_at: string;
  // Протокол: описание находок «поле → значение»; report_text — как уходит в AI
  sr_fields: { name: string; value: string }[];
  report_text: string;
  patient: PatientBrief;
  doctor: DoctorBrief;
  ai: Inference | null;
  decision: Decision | null;
  notification: Notification | null;
  appointments: CardAppointment[]; // записи пациента по уведомлению
  requirements: Requirement[];
  ai_retry: AIRetry | null; // есть, пока AI не ответил после сбоя
  ai_auto: boolean; // автоотправка в AI включена; false — врач отправляет кнопкой
  ai_send_after: string | null; // раньше этого времени повторно отправить в AI нельзя
  can_act: boolean;
}

export interface AuditEvent {
  id: string;
  action: string;
  at: string;
  actor_id: string | null;
  actor_role: string | null;
  actor_name: string | null;
  payload: Record<string, unknown>;
  request_id: string | null;
}

// --- Кабинет пациента ---

export interface PatientNotification {
  notification: Notification;
  recommendations: RecommendationType[];
  details: RecommendationDetails;
  comment: string | null;
  study: { id: string; study_type: StudyType; body_region: string; performed_at: string };
  treating_doctor: DoctorBrief;
  requirements: Requirement[];
  booking: BookingProgress | null;
  appointments: CardAppointment[];
  explanation: { summary: string; terms: { term: string; explanation: string }[] } | null;
}

export interface DaySlots {
  date: string; // YYYY-MM-DD
  slots: string[]; // UTC
}

export interface AppointmentIn {
  // Врач или кабинет исследования — одно из двух
  doctor_id?: string | null;
  research_type?: string | null;
  scheduled_for: string; // ISO с часовым поясом
  notification_id?: string | null;
  requirement?: string | null; // ключ направления — обязательно с notification_id
}

export interface Appointment {
  id: string;
  status: AppointmentStatus;
  scheduled_for: string;
  created_at: string;
  notification_id: string | null;
  study_id: string | null;
  requirement: string | null;
  doctor: DoctorBrief | null; // null — запись на исследование
  research_type: string | null;
  patient: { id: string; full_name: string; phone: string };
}

// --- Личный кабинет ---

export interface Account {
  id: string;
  role: Role;
  full_name: string;
  email: string;
  specialty: string | null;
  // Только у пациента
  birth_date: string | null;
  phone: string | null;
  contact_email: string | null; // почта для уведомлений; null — email входа
  notify_channels: NotificationChannel[];
  available_channels: NotificationChannel[]; // есть контакт для канала
}

export interface AccountPatch {
  email?: string;
  phone?: string;
  contact_email?: string; // "" — уведомления на email входа
  notify_channels?: NotificationChannel[];
}

// --- Главврач: врачи ---

export interface StaffDoctor {
  id: string;
  full_name: string;
  email: string;
  specialty: string | null;
  active: boolean;
  open_studies: number; // ждут решения
  decisions: number;
  upcoming_appointments: number; // записи на ближайшие 7 дней
}

export interface StaffDoctorIn {
  full_name: string;
  email: string;
  specialty: string;
  password: string;
}

export type StaffDoctorPatch = Partial<Pick<StaffDoctor, "full_name" | "specialty" | "active">>;

// --- Дашборд ---

export interface Rate {
  agreed: number;
  total: number;
  rate: number | null;
}

export interface Dashboard {
  summary: {
    studies_total: number;
    studies_by_status: Record<string, number>;
    decisions_total: number;
    decisions_without_ai: number;
    ai_runs: number;
    ai_failures: number;
  };
  agreement: Rate;
  agreement_by_confidence: { threshold: number; high: Rate; low: Rate };
  details_agreement: Rate;
  confusion_matrix: { labels: string[]; matrix: number[][] };
  latency: { count: number; avg_ms: number | null; p95_ms: number | null };
  by_doctor: (Rate & {
    doctor_id: string;
    full_name: string;
    specialty: string | null;
    decisions: number;
    details_agreed: number;
    details_total: number;
    details_rate: number | null; // полное совпадение с AI (тип + специалист/исследования)
  })[];
  /** Воронка после уведомления; scope — "all" или тип направления. */
  funnel: {
    scope: string;
    sent: number;
    read: number;
    booked_any: number;
    booked_all: number;
    declined: number;
  }[];
  notifications: {
    recommendation: string;
    sent: number;
    booked: number;
    declined: number;
    pending: number;
    booked_rate: number | null;
  }[];
  recent_decisions: {
    decision_id: string;
    study_id: string;
    study_type: string;
    patient_name: string;
    doctor_name: string;
    ai_recommendation: string | null;
    ai_confidence: number | null;
    chosen_types: string[];
    accepted_ai: boolean | null;
    details_match: boolean | null;
    created_at: string;
  }[];
}
