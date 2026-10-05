"use client";

import { BellRing, CalendarCheck, CalendarX, Circle, Send } from "lucide-react";
import { useState } from "react";

import { NotificationHistory } from "@/components/notification-history";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { errorMessage } from "@/lib/api/client";
import { useRemind } from "@/lib/api/hooks";
import type { StudyCard } from "@/lib/api/types";
import {
  CHANNEL_LABELS,
  fmtDateTime,
  useAppointmentTarget,
  useRequirementLabel,
} from "@/lib/format";
import { cn } from "@/lib/utils";

/** Уведомление пациента: уходит автоматически после решения во все доступные каналы. */
export function NotifyPanel({ study }: { study: StudyCard }) {
  const requirementLabel = useRequirementLabel();
  const appointmentTarget = useAppointmentTarget();
  const remind = useRemind(study.id);
  const n = study.notification;
  // Уведомление появилось на глазах (врач только что принял решение) — подсвечиваем панель
  const [sentNow] = useState(!n);
  if (!n) return null;
  const urgent = study.decision?.chosen_types.includes("urgent_hospitalization");
  const sms = n.deliveries.find((d) => d.attempt === 0 && d.channel === "sms")?.text;
  // Каналы — по настоящим отправкам этого уведомления (у демо-данных их нет)
  const sentTo = [...new Set(n.deliveries.filter((d) => d.attempt === 0).map((d) => d.channel))];
  // Как rules.needs_reminder на backend: есть незакрытые направления, пациент не отказался
  const canRemind =
    study.can_act &&
    n.patient_action !== "declined" &&
    study.requirements.some((r) => !r.appointment_id) &&
    n.reminders_sent < n.max_reminders;

  return (
    <Card className={cn(sentNow && "animate-notify-sent")}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BellRing className="size-5 text-primary" /> Уведомление пациента
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-muted-foreground">Уведомление {fmtDateTime(n.sent_at)}:</span>
          {sentTo.map((c) => (
            <Badge key={c} variant="outline">
              {CHANNEL_LABELS[c]}
            </Badge>
          ))}
          <Badge variant="outline">Личный кабинет</Badge>
          {n.read_at ? (
            <Badge className="bg-sky-100 text-sky-800">прочитано</Badge>
          ) : (
            <Badge variant="secondary">не прочитано</Badge>
          )}
        </div>
        <div className="grid gap-1">
          <span className="text-xs font-medium text-muted-foreground">На сайте, в кабинете:</span>
          <p className="rounded-xl bg-background p-3 whitespace-pre-line">{n.text}</p>
        </div>
        <div className="grid gap-1">
          <span className="text-xs font-medium text-muted-foreground">
            В email — коротко, со ссылкой:
          </span>
          <p className="rounded-xl bg-background p-3">{n.short_text}</p>
        </div>
        {sms && (
          <div className="grid gap-1">
            <span className="text-xs font-medium text-muted-foreground">
              В SMS — ещё короче, без медицинских данных:
            </span>
            <p className="rounded-xl bg-background p-3">{sms}</p>
          </div>
        )}
        {n.deliveries.length > 0 ? (
          <details className="group">
            <summary className="cursor-pointer list-none font-medium text-primary">
              История отправок и напоминания
              {n.reminders_sent > 0 && ` (напоминаний: ${n.reminders_sent})`}
            </summary>
            <div className="mt-3">
              <NotificationHistory notification={n} staff />
            </div>
          </details>
        ) : (
          <p className="text-muted-foreground">
            По SMS и email не отправлялось — уведомление в личном кабинете
            {n.next_reminder_at && `; напоминание — ${fmtDateTime(n.next_reminder_at)}`}
          </p>
        )}
        {canRemind && (
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="outline"
              disabled={remind.isPending}
              onClick={() => remind.mutate(n.id)}
            >
              <Send /> Напомнить сейчас
            </Button>
            <span className="text-muted-foreground">
              {remind.isError
                ? errorMessage(remind.error)
                : `Напоминание ${n.reminders_sent + 1} из ${n.max_reminders} — во все каналы`}
            </span>
          </div>
        )}

        {study.requirements.length > 0 && (
          <div className="grid gap-1.5">
            <div className="text-muted-foreground">
              Запись пациента: {study.requirements.filter((r) => r.appointment_id).length} из{" "}
              {study.requirements.length}
              {study.status === "completed" && " — все направления закрыты"}
            </div>
            {study.requirements.map((r) => (
              <div
                key={r.key}
                className={cn(
                  "flex items-center gap-2 rounded-lg p-3",
                  r.appointment_id ? "bg-emerald-50 text-emerald-900" : "bg-background",
                )}
              >
                {r.appointment_id ? (
                  <CalendarCheck className="size-4 shrink-0" />
                ) : (
                  <Circle className="size-4 shrink-0 text-muted-foreground" />
                )}
                <span>
                  <span className="font-medium">{requirementLabel(r)}</span>
                  {r.appointment_id && r.scheduled_for ? (
                    <>
                      {" "}
                      — {r.doctor ? `${r.doctor.full_name}, ` : ""}
                      {fmtDateTime(r.scheduled_for)}
                    </>
                  ) : (
                    <span className="text-muted-foreground"> — ещё не записан</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        )}
        {study.appointments
          .filter((a) => a.status === "cancelled")
          .map((a) => (
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
        {n.patient_action === "declined" && (
          <div className="flex items-center gap-2 rounded-lg bg-red-50 p-3 text-red-900">
            <CalendarX className="size-4 shrink-0" /> Пациент отказался
          </div>
        )}
        {study.requirements.length === 0 && !n.patient_action ? (
          <div className="text-muted-foreground">
            {urgent
              ? "Экстренная госпитализация — запись не нужна, кейс закрыт"
              : "Патологии не выявлено — записываться не нужно, кейс закрыт"}
          </div>
        ) : (
          !n.patient_action && <div className="text-muted-foreground">Пациент ещё не ответил</div>
        )}
      </CardContent>
    </Card>
  );
}
