"use client";

import {
  BellRing,
  CalendarCheck,
  CalendarPlus,
  CalendarX,
  Circle,
  CircleCheck,
  ClipboardList,
  Loader2,
  Stethoscope,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/app-shell";
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

  const items = notifications.data ?? [];
  // Сверху — где ещё нужна запись: не все направления закрыты записью
  const needsAction = (n: PatientNotification) =>
    n.notification.patient_action !== "declined" &&
    !!n.booking &&
    n.booking.booked < n.booking.required;
  const sortedItems = [...items].sort((a, b) => Number(needsAction(b)) - Number(needsAction(a)));

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
        {notifications.data && !items.length && (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              Новых рекомендаций нет
            </CardContent>
          </Card>
        )}
        {sortedItems.map((n) => (
          <NotificationCard key={n.notification.id} item={n} />
        ))}
      </section>

      <section className="grid gap-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-xl font-medium">
            <ClipboardList className="size-5 text-primary" /> Мои записи
          </h2>
          <Button variant="outline" size="sm" onClick={() => setBookingFree(true)}>
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
  // Записаться нужно по каждому направлению; после отказа — нельзя
  const canBook = n.patient_action !== "declined";
  const progress = item.booking;
  const done = !!progress && progress.booked === progress.required;
  const cancelled = item.appointments.filter((a) => a.status === "cancelled");

  return (
    <Card className={cn(canBook && !done && "ring-2 ring-primary/30")}>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <CardTitle className="text-lg">
              {label("study_types", item.study.study_type)},{" "}
              {label("body_regions", item.study.body_region).toLowerCase()}
            </CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              исследование от {fmtDate(item.study.performed_at)}
            </p>
          </div>
          {open && <Badge>Новое</Badge>}
          {canBook && progress && progress.booked > 0 && (
            <Badge className={done ? "bg-emerald-100 text-emerald-800" : undefined}>
              {done ? "Вы записаны" : `Записано ${progress.booked} из ${progress.required}`}
            </Badge>
          )}
          {n.patient_action === "declined" && <Badge variant="secondary">Вы отказались</Badge>}
        </div>
      </CardHeader>
      <CardContent className="grid gap-4 text-sm">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Stethoscope className="size-4" />
          Лечащий врач: {item.treating_doctor.full_name} (
          {label("specialists", item.treating_doctor.specialty)})
        </div>
        {item.comment && (
          <blockquote className="border-l-2 border-primary/40 pl-3 italic">
            {item.comment}
          </blockquote>
        )}
        <p className="rounded-xl bg-background p-3 text-muted-foreground">
          <span className="font-medium text-foreground">{channelsText(n.channels)}:</span> {n.text}
        </p>

        <div className="grid gap-2">
          <h3 className="font-medium">
            {canBook && !done ? "Запишитесь по каждому направлению" : "Направления врача"}
          </h3>
          {item.requirements.map((r) => (
            <div key={r.key} className="grid gap-2">
              <div
                className={cn(
                  "flex flex-wrap items-center justify-between gap-2 rounded-xl p-3",
                  r.appointment_id ? "bg-emerald-50 text-emerald-900" : "bg-background",
                )}
              >
                <div className="flex items-center gap-2">
                  {r.appointment_id ? (
                    <CircleCheck className="size-4 shrink-0" />
                  ) : (
                    <Circle className="size-4 shrink-0 text-muted-foreground" />
                  )}
                  <div>
                    <div className="font-medium">{requirementLabel(r)}</div>
                    {r.appointment_id && r.scheduled_for ? (
                      <div className="text-xs">
                        {r.doctor ? `${r.doctor.full_name}, ` : ""}
                        {fmtDateTime(r.scheduled_for)}
                      </div>
                    ) : (
                      r.kind === "treating" &&
                      r.doctor && (
                        <div className="text-xs text-muted-foreground">{r.doctor.full_name}</div>
                      )
                    )}
                  </div>
                </div>
                {canBook && !r.appointment_id && bookingKey !== r.key && (
                  <Button size="sm" onClick={() => setBookingKey(r.key)}>
                    <CalendarPlus /> Записаться
                  </Button>
                )}
              </div>
              {canBook && bookingKey === r.key && (
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
          ))}
        </div>

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

        {open && (
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
