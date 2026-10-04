"use client";

import {
  BellRing,
  CalendarCheck,
  CalendarPlus,
  CalendarX,
  Circle,
  CircleCheck,
  ClipboardList,
  MessageCircleQuestion,
  Siren,
  Loader2,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { NotificationHistory } from "@/components/notification-history";
import { BookingPanel } from "@/components/patient/booking-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api/client";
import {
  useAppointments,
  useCancelAppointment,
  useDecline,
  useExplain,
  useMarkRead,
  useMyNotifications,
} from "@/lib/api/hooks";
import type { Appointment, PatientNotification } from "@/lib/api/types";
import { useAuth } from "@/lib/auth";
import {
  channelsText,
  fmtDate,
  fmtDateTime,
  useAppointmentTarget,
  useLabels,
  useRequirementLabel,
} from "@/lib/format";
import { cn } from "@/lib/utils";

export default function PatientPage() {
  return (
    <AppShell roles={["patient"]}>
      <PatientCabinet />
    </AppShell>
  );
}

function PatientCabinet() {
  const { user } = useAuth();
  const notifications = useMyNotifications();
  const appointments = useAppointments();
  const { mutate: markRead } = useMarkRead();
  const [bookingFree, setBookingFree] = useState(false);

  // Открыл кабинет — уведомления прочитаны (один раз на уведомление)
  const marked = useRef(new Set<string>());
  useEffect(() => {
    for (const n of notifications.data ?? []) {
      const id = n.notification.id;
      if (n.notification.status === "sent" && !marked.current.has(id)) {
        marked.current.add(id);
        markRead(id);
      }
    }
  }, [notifications.data, markRead]);

  // Переход с экрана «Исследования» (#n-<id>) — прокручиваем к нужной карточке, когда она есть
  const hasData = !!notifications.data;
  useEffect(() => {
    if (!hasData || !window.location.hash) return;
    document.querySelector(window.location.hash)?.scrollIntoView({ block: "start" });
  }, [hasData]);

  const items = notifications.data ?? [];
  // На виду — только где ещё нужна запись, и новые (прочитаны в этот заход: пациент должен
  // увидеть и «патологии не выявлено»). Остальное — в «Завершённых» и на экране «Исследования»
  const [openedAt] = useState(() => Date.now());
  const needsAction = (n: PatientNotification) =>
    n.notification.patient_action !== "declined" &&
    !!n.booking &&
    n.booking.booked < n.booking.required;
  const isNew = (n: PatientNotification) =>
    !n.notification.read_at || Date.parse(n.notification.read_at) >= openedAt - 5000;
  const active = items.filter((n) => needsAction(n) || isNew(n));
  const finished = items.filter((n) => !active.includes(n));
  // Переход с экрана «Исследования» к завершённой рекомендации — сразу раскрываем список
  const [showFinished, setShowFinished] = useState(
    () => typeof window !== "undefined" && window.location.hash.startsWith("#n-"),
  );

  return (
    <div className="mx-auto grid max-w-4xl gap-6">
      <div>
        <h1 className="text-3xl font-medium tracking-tight md:text-4xl">
          Здравствуйте, {user?.full_name.split(" ").slice(1).join(" ") || user?.full_name}
        </h1>
        <p className="text-sm text-muted-foreground">
          Здесь рекомендации врача по вашим исследованиям и записи на приём.
        </p>
      </div>

      <section className="grid gap-3">
        <h2 className="flex items-center gap-2 text-xl font-medium">
          <BellRing className="size-5 text-primary" /> Рекомендации врача
        </h2>
        {notifications.isLoading && <Skeleton className="h-48" />}
        {notifications.isError && (
          <p className="text-sm text-destructive">{errorMessage(notifications.error)}</p>
        )}
        {notifications.data && !active.length && (
          <Card>
            <CardContent className="py-8 text-center text-muted-foreground">
              Новых рекомендаций нет — по всем вы записаны или они не требуют записи.
            </CardContent>
          </Card>
        )}
        {active.map((n) => (
          <NotificationCard key={n.notification.id} item={n} />
        ))}
        {finished.length > 0 && (
          <Button
            variant="outline"
            className="justify-self-start"
            onClick={() => setShowFinished((v) => !v)}
          >
            {showFinished ? <ChevronUp /> : <ChevronDown />}
            {showFinished ? "Скрыть завершённые" : `Завершённые рекомендации (${finished.length})`}
          </Button>
        )}
        {showFinished && finished.map((n) => <NotificationCard key={n.notification.id} item={n} />)}
      </section>

      <section className="grid gap-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-xl font-medium">
            <ClipboardList className="size-5 text-primary" /> Мои записи
          </h2>
          <Button size="lg" className="shadow-sm" onClick={() => setBookingFree(true)}>
            <CalendarPlus /> Записаться к врачу
          </Button>
        </div>
        <AppointmentsList items={appointments.data} loading={appointments.isLoading} />
      </section>

      <Dialog open={bookingFree} onOpenChange={setBookingFree}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Запись к врачу</DialogTitle>
          </DialogHeader>
          <BookingPanel onDone={() => setBookingFree(false)} />
        </DialogContent>
      </Dialog>
    </div>
  );
}

function NotificationCard({ item }: { item: PatientNotification }) {
  const label = useLabels();
  const requirementLabel = useRequirementLabel();
  const appointmentTarget = useAppointmentTarget();
  const decline = useDecline();
  const [bookingKey, setBookingKey] = useState<string | null>(null);
  const n = item.notification;
  const open = !n.patient_action;
  const declined = n.patient_action === "declined";
  const progress = item.booking;
  const done = !!progress && progress.booked === progress.required;
  // «Патологии не выявлено»: направлений нет — записываться не нужно
  const nothingToBook = item.requirements.length === 0;
  const urgent = item.recommendations.includes("urgent_hospitalization");
  const needsBooking = !declined && !done && !nothingToBook;
  const cancelled = item.appointments.filter((a) => a.status === "cancelled");

  return (
    <Card id={`n-${n.id}`} className={cn(needsBooking && "ring-2 ring-primary/40")}>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <CardTitle className="text-lg">
              {label("study_types", item.study.study_type)},{" "}
              {label("body_regions", item.study.body_region).toLowerCase()}
            </CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              исследование от {fmtDate(item.study.performed_at)} · лечащий врач{" "}
              {item.treating_doctor.full_name}
            </p>
          </div>
          {open && <Badge>Новое</Badge>}
        </div>
      </CardHeader>
      <CardContent className="grid gap-4 text-sm">
        {/* Итог — крупно и сразу: что сказал врач и что делать пациенту */}
        {urgent ? (
          <Summary
            tone="urgent"
            icon={<Siren className="size-6" />}
            title="Срочно обратитесь в стационар"
          >
            Врач рекомендует экстренную госпитализацию. При ухудшении самочувствия звоните 103 или
            112.
          </Summary>
        ) : nothingToBook ? (
          <Summary
            tone="ok"
            icon={<CircleCheck className="size-6" />}
            title="Патологии не выявлено"
          >
            Записываться на приём не нужно.
          </Summary>
        ) : declined ? (
          <Summary
            tone="muted"
            icon={<CalendarX className="size-6" />}
            title="Вы отказались от записи"
          >
            Если передумаете — запишитесь к врачу в разделе «Мои записи».
          </Summary>
        ) : done ? (
          <Summary
            tone="ok"
            icon={<CircleCheck className="size-6" />}
            title="Вы записаны по всем направлениям"
          >
            Ждём вас на приёме.
          </Summary>
        ) : (
          <Summary
            tone="primary"
            icon={<ClipboardList className="size-6" />}
            title="Врач рекомендует записаться"
          >
            {item.requirements.map((r) => requirementLabel(r)).join(" · ")}
            {progress && (
              <div className="mt-3 grid gap-1">
                <div className="flex justify-between text-xs">
                  <span>
                    Записано {progress.booked} из {progress.required}
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-background">
                  <div
                    className="h-full rounded-full bg-primary transition-[width]"
                    style={{ width: `${(progress.booked / progress.required) * 100}%` }}
                  />
                </div>
              </div>
            )}
          </Summary>
        )}

        {/* Подробное сообщение врача — крупно; в SMS и мессенджеры ушло короткое со ссылкой */}
        <p className="rounded-2xl bg-background p-4 text-base leading-relaxed whitespace-pre-line">
          {n.text}
        </p>

        <Explanation item={item} />

        {!nothingToBook && (
          <div className="grid gap-2">
            {item.requirements.map((r) => {
              const booked = !!r.appointment_id;
              return (
                <div key={r.key} className="grid gap-2">
                  <div
                    className={cn(
                      "flex flex-wrap items-center justify-between gap-3 rounded-xl p-3",
                      booked
                        ? "bg-emerald-50 text-emerald-900"
                        : declined
                          ? "bg-background"
                          : "border-2 border-primary/40 bg-background",
                    )}
                  >
                    <div className="flex items-center gap-2">
                      {booked ? (
                        <CircleCheck className="size-5 shrink-0" />
                      ) : (
                        <Circle className="size-5 shrink-0 text-muted-foreground" />
                      )}
                      <div>
                        <div className="font-medium">{requirementLabel(r)}</div>
                        {booked && r.scheduled_for ? (
                          <div className="text-xs">
                            {r.doctor ? `${r.doctor.full_name}, ` : ""}
                            {fmtDateTime(r.scheduled_for)}
                          </div>
                        ) : (
                          r.kind === "treating" &&
                          r.doctor && (
                            <div className="text-xs text-muted-foreground">
                              {r.doctor.full_name}
                            </div>
                          )
                        )}
                      </div>
                    </div>
                    {!declined && !booked && bookingKey !== r.key && (
                      <Button size="lg" className="shadow-sm" onClick={() => setBookingKey(r.key)}>
                        <CalendarPlus /> Записаться
                      </Button>
                    )}
                  </div>
                  {!declined && bookingKey === r.key && (
                    <div className="rounded-2xl border bg-card p-4">
                      <BookingPanel
                        target={
                          r.kind === "treating"
                            ? { kind: "treating", doctor: item.treating_doctor }
                            : { kind: r.kind, code: r.code! }
                        }
                        notificationId={n.id}
                        requirement={r.key}
                        onDone={() => setBookingKey(null)}
                      />
                      <Button
                        variant="ghost"
                        size="sm"
                        className="mt-2"
                        onClick={() => setBookingKey(null)}
                      >
                        Отмена
                      </Button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {cancelled.map((a) => (
          <div
            key={a.id}
            className="flex items-center gap-2 rounded-lg bg-background p-3 text-muted-foreground"
          >
            <CalendarX className="size-4 shrink-0" />
            <span className="line-through">
              {appointmentTarget(a)}, {fmtDateTime(a.scheduled_for)}
            </span>
            <span className="text-xs">отменена</span>
          </div>
        ))}

        {/* Уведомление и напоминания — по запросу, чтобы не отвлекать от итога */}
        <details className="group rounded-xl bg-background p-3">
          <summary className="flex cursor-pointer list-none items-center gap-2 font-medium">
            <BellRing className="size-4 text-primary" />
            Отправлено в {channelsText(n.channels)}
            {n.reminders_sent > 0 && (
              <span className="font-normal text-muted-foreground">
                · напоминаний {n.reminders_sent}
              </span>
            )}
            <ChevronDown className="ml-auto size-4 transition-transform group-open:rotate-180" />
          </summary>
          <div className="mt-3 grid gap-3">
            <NotificationHistory notification={n} />
          </div>
        </details>

        {open && !nothingToBook && (
          <div className="flex justify-end">
            <DeclineButton pending={decline.isPending} onConfirm={() => decline.mutate(n.id)} />
          </div>
        )}
        {decline.isError && (
          <p className="text-right text-sm text-destructive">{errorMessage(decline.error)}</p>
        )}
      </CardContent>
    </Card>
  );
}

const SUMMARY_TONES = {
  urgent: "bg-red-600 text-white",
  primary: "bg-primary/10 text-foreground [&_svg]:text-primary",
  ok: "bg-emerald-50 text-emerald-900",
  muted: "bg-background text-muted-foreground",
} as const;

/** «Что значит ваше заключение» — B2C AI-команды; запрашивается один раз при открытии. */
function Explanation({ item }: { item: PatientNotification }) {
  const explain = useExplain();
  const asked = useRef(false);
  const id = item.notification.id;
  const ready = item.explanation;
  const { mutate } = explain;
  useEffect(() => {
    if (!ready && !asked.current) {
      asked.current = true;
      mutate(id);
    }
  }, [ready, id, mutate]);

  return (
    <section className="grid gap-2 rounded-2xl border bg-card p-4">
      <h3 className="flex items-center gap-2 font-medium">
        <MessageCircleQuestion className="size-5 text-primary" /> Что значит ваше заключение
      </h3>
      {ready ? (
        <>
          <p className="text-base leading-relaxed">{ready.summary}</p>
          {ready.terms.length > 0 && (
            <dl className="grid gap-1.5">
              {ready.terms.map((t) => (
                <div key={t.term}>
                  <dt className="inline font-medium">{t.term}</dt>
                  <dd className="inline text-muted-foreground"> — {t.explanation}</dd>
                </div>
              ))}
            </dl>
          )}
          <p className="text-xs text-muted-foreground">
            Объяснение подготовил AI-ассистент по тексту заключения. Решение о лечении принимает
            врач.
          </p>
        </>
      ) : explain.isError ? (
        <p className="text-muted-foreground">
          Объяснение пока недоступно. Рекомендации врача — ниже.
        </p>
      ) : (
        <p className="inline-flex items-center gap-2 text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Готовим объяснение простым языком…
        </p>
      )}
    </section>
  );
}

/** Крупный итог карточки: что сказал врач и что делать пациенту. */
function Summary({
  tone,
  icon,
  title,
  children,
}: {
  tone: keyof typeof SUMMARY_TONES;
  icon: React.ReactNode;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className={cn("flex gap-3 rounded-2xl p-4", SUMMARY_TONES[tone])}>
      <span className="shrink-0">{icon}</span>
      <div className="min-w-0 flex-1">
        <div className="text-lg font-medium">{title}</div>
        {children && <div className="mt-0.5">{children}</div>}
      </div>
    </div>
  );
}

function DeclineButton({ pending, onConfirm }: { pending: boolean; onConfirm: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)} disabled={pending}>
        Не буду записываться
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Отказаться от рекомендации?</DialogTitle>
            <DialogDescription>
              Лечащий врач увидит ваш отказ. Записаться к врачу можно и позже через «Мои записи».
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>Назад</DialogClose>
            <Button
              variant="destructive"
              onClick={() => {
                setOpen(false);
                onConfirm();
              }}
            >
              Отказаться
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function AppointmentsList({ items, loading }: { items?: Appointment[]; loading: boolean }) {
  const target = useAppointmentTarget();
  const cancel = useCancelAppointment();
  const [now] = useState(() => Date.now()); // «прошла» — относительно открытия страницы
  const [showCancelled, setShowCancelled] = useState(false);
  if (loading) return <Skeleton className="h-20" />;
  const cancelledCount = items?.filter((a) => a.status === "cancelled").length ?? 0;
  const visible = (items ?? []).filter((a) => showCancelled || a.status !== "cancelled");
  const toggle = cancelledCount > 0 && (
    <Button
      variant="link"
      size="sm"
      className="justify-self-start px-0 text-muted-foreground"
      onClick={() => setShowCancelled((v) => !v)}
    >
      {showCancelled ? "Скрыть отменённые" : `Показать отменённые (${cancelledCount})`}
    </Button>
  );
  if (!visible.length)
    return (
      <div className="grid gap-1">
        <Card>
          <CardContent className="py-6 text-center text-sm text-muted-foreground">
            Записей нет
          </CardContent>
        </Card>
        {toggle}
      </div>
    );

  const sorted = [...visible].sort(
    (a, b) =>
      Number(a.status === "cancelled") - Number(b.status === "cancelled") ||
      a.scheduled_for.localeCompare(b.scheduled_for),
  );

  return (
    <div className="grid gap-1">
      <Card className="py-0">
        <CardContent className="divide-y px-0">
          {sorted.map((a) => {
            const cancelled = a.status === "cancelled";
            const past = new Date(a.scheduled_for).getTime() < now;
            return (
              <div
                key={a.id}
                className={cn(
                  "flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-sm",
                  (cancelled || past) && "text-muted-foreground",
                )}
              >
                <div className="flex items-center gap-3">
                  {cancelled ? (
                    <CalendarX className="size-5" />
                  ) : (
                    <CalendarCheck className="size-5 text-primary" />
                  )}
                  <div>
                    <div className={cn("font-medium", cancelled && "line-through")}>
                      {fmtDateTime(a.scheduled_for)}
                    </div>
                    <div className="text-xs">{target(a)}</div>
                  </div>
                </div>
                {cancelled ? (
                  <Badge variant="secondary">Отменена</Badge>
                ) : past ? (
                  <Badge variant="outline">Прошла</Badge>
                ) : (
                  <span className="flex items-center gap-2">
                    {cancel.isError && cancel.variables === a.id && (
                      <span className="text-xs text-destructive">{errorMessage(cancel.error)}</span>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={cancel.isPending}
                      onClick={() => cancel.mutate(a.id)}
                    >
                      {cancel.isPending && cancel.variables === a.id && (
                        <Loader2 className="animate-spin" />
                      )}
                      Отменить
                    </Button>
                  </span>
                )}
              </div>
            );
          })}
        </CardContent>
      </Card>
      {toggle}
    </div>
  );
}
