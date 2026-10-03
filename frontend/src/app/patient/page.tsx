"use client";

import {
  BellRing,
  CalendarCheck,
  CalendarPlus,
  CalendarX,
  ClipboardList,
  Loader2,
  Stethoscope,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

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
import { channelsText, fmtDate, fmtDateTime, useDecisionItems, useLabels } from "@/lib/format";
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
  // Сверху — где ещё нужна запись: нет ответа или нет действующей записи по уведомлению
  const needsAction = (n: PatientNotification) =>
    n.notification.patient_action !== "declined" &&
    !n.appointments.some((a) => a.status === "scheduled");
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
  const recs = useDecisionItems()(item.recommendations, item.details);
  const decline = useDecline();
  const [booking, setBooking] = useState(false);
  const n = item.notification;
  const open = !n.patient_action;
  const scheduled = item.appointments.filter((a) => a.status === "scheduled");
  // По одному уведомлению можно записаться к нескольким врачам; после отказа — нельзя
  const canBook = n.patient_action !== "declined";
  const highlight = canBook && !scheduled.length;

  return (
    <Card className={cn(highlight && "ring-2 ring-primary/30")}>
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
          {scheduled.length > 0 && (
            <Badge className="bg-emerald-100 text-emerald-800">Вы записаны</Badge>
          )}
          {n.patient_action === "booked" && !scheduled.length && (
            <Badge variant="secondary">Запись отменена</Badge>
          )}
          {n.patient_action === "declined" && <Badge variant="secondary">Вы отказались</Badge>}
        </div>
      </CardHeader>
      <CardContent className="grid gap-4 text-sm">
        <ul className="grid gap-1.5">
          {recs.map((r) => (
            <li key={r.type} className="rounded-xl bg-background px-3 py-2">
              <span className="font-medium">{r.label}</span>
              {r.text && <span className="text-muted-foreground"> — {r.text}</span>}
            </li>
          ))}
        </ul>
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

        {item.appointments.map((a) => (
          <div
            key={a.id}
            className={cn(
              "flex items-center gap-2 rounded-lg p-3",
              a.status === "cancelled"
                ? "bg-background text-muted-foreground line-through"
                : "bg-emerald-50 text-emerald-900",
            )}
          >
            <CalendarCheck className="size-4 shrink-0" />
            {a.doctor.full_name} ({label("specialists", a.doctor.specialty)}),{" "}
            {fmtDateTime(a.scheduled_for)}
          </div>
        ))}

        {canBook && !booking && (
          <div className="flex flex-wrap justify-end gap-2">
            {open && (
              <DeclineButton
                pending={decline.isPending}
                onConfirm={() =>
                  decline.mutate(n.id, {
                    onSuccess: () => toast("Вы отказались от рекомендации"),
                    onError: (err) => toast.error(errorMessage(err)),
                  })
                }
              />
            )}
            <Button
              variant={item.appointments.length ? "outline" : "default"}
              onClick={() => setBooking(true)}
            >
              <CalendarPlus />{" "}
              {item.appointments.length ? "Записаться ещё к врачу" : "Записаться на приём"}
            </Button>
          </div>
        )}

        {canBook && booking && (
          <div className="rounded-2xl border bg-card p-4">
            <BookingPanel
              notificationId={n.id}
              suggested={item.suggested_doctors}
              suggestedSpecialties={item.suggested_specialties}
              lockedDoctor={item.only_treating_doctor ? item.treating_doctor : undefined}
              onDone={() => setBooking(false)}
            />
            <Button variant="ghost" size="sm" className="mt-2" onClick={() => setBooking(false)}>
              Отмена
            </Button>
          </div>
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
  const label = useLabels();
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
                    <div className="text-xs">
                      {a.doctor.full_name}, {label("specialists", a.doctor.specialty)}
                    </div>
                  </div>
                </div>
                {cancelled ? (
                  <Badge variant="secondary">Отменена</Badge>
                ) : past ? (
                  <Badge variant="outline">Прошла</Badge>
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={cancel.isPending}
                    onClick={() =>
                      cancel.mutate(a.id, {
                        onSuccess: () => toast("Запись отменена"),
                        onError: (err) => toast.error(errorMessage(err)),
                      })
                    }
                  >
                    {cancel.isPending && cancel.variables === a.id && (
                      <Loader2 className="animate-spin" />
                    )}
                    Отменить
                  </Button>
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
