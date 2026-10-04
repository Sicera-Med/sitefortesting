// Типы API — вручную по backend/app/schemas (SPEC §7). Время — ISO-строки в UTC.

export type Role = "chief" | "manager" | "doctor" | "patient";
export type Sex = "m" | "f";
export type StudyType = "xray" | "ct" | "mri" | "ultrasound" | "mammography";
export type StudyStatus = "new" | "ai_ready" | "ai_failed" | "decided" | "notified" | "completed";
export type RecommendationType =
  "repeat_appointment" | "specialist_consult" | "additional_research";
export type AISource = "mock" | "http" | "manual";
export type NotificationChannel = "sms" | "email" | "social";
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
  score: number;
}

export interface Reason {
  code: string;
  label: string;
  weight: number;
}

/** Детали, которые предлагает AI или выбирает врач (SPEC §5.5, §6.2). */
export interface RecommendationDetails {
  specialists?: string[];
  research_types?: string[];
}

export interface Inference {
  id: string;
  source: AISource;
  request_id: string;
  model_name: string;
  model_version: string;
  recommendation: RecommendationType;
  confidence: number;
  ranked_options: RankedOption[];
  reasons: Reason[];
  details: RecommendationDetails;
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
  text: string;
  status: NotificationStatus;
  sent_at: string;
  read_at: string | null;
  patient_action: PatientActionType | null;
  action_at: string | null;
  appointment_id: string | null;
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
  ai: { recommendation: RecommendationType; confidence: number } | null;
  decision: { chosen_types: RecommendationType[]; accepted_ai: boolean | null } | null;
  booking: BookingProgress | null; // сколько направлений пациент закрыл записью
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

export interface StudyCard {
  id: string;
  status: StudyStatus;
  study_type: StudyType;
  body_region: string;
  performed_at: string;
  created_at: string;
  report_text: string;
  patient: PatientBrief;
  doctor: DoctorBrief;
  ai: Inference | null;
  decision: Decision | null;
  notification: Notification | null;
  appointments: CardAppointment[]; // записи пациента по уведомлению
  requirements: Requirement[];
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
  social: string | null;
  notify_channels: NotificationChannel[];
  available_channels: NotificationChannel[]; // есть контакт для канала
}

export interface AccountPatch {
  email?: string;
  phone?: string;
  social?: string;
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
  })[];
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
