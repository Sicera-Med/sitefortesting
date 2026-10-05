"use client";

import {
  BellRing,
  CalendarCheck,
  CalendarPlus,
  CalendarX,
  ClipboardList,
  Loader2,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { BookingPanel } from "@/components/patient/booking-panel";
import { NotificationCard } from "@/components/patient/notification-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api/client";
import {
  useAppointments,
  useCancelAppointment,
  useMarkRead,
  useMyNotifications,
} from "@/lib/api/hooks";
import type { Appointment, PatientNotification } from "@/lib/api/types";
import { useAuth } from "@/lib/auth";
import { fmtDateTime, useAppointmentTarget } from "@/lib/format";
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
