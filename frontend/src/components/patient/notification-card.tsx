"use client";

// Карточка рекомендации врача в кабинете пациента: итог, чек-лист направлений, запись.

import { CalendarPlus, CalendarX, Circle, CircleCheck, ClipboardList, Siren } from "lucide-react";
import { useState } from "react";

import { BookingPanel } from "@/components/patient/booking-panel";
import { Explanation } from "@/components/patient/explanation";
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
import { errorMessage } from "@/lib/api/client";
import { useDecline } from "@/lib/api/hooks";
import type { PatientNotification } from "@/lib/api/types";
import {
  fmtDate,
  fmtDateTime,
  useAppointmentTarget,
  useLabels,
  useRequirementLabel,
} from "@/lib/format";
import { cn } from "@/lib/utils";

export function NotificationCard({ item }: { item: PatientNotification }) {
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
