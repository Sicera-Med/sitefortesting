"use client";

import { BellRing, CalendarCheck, CalendarX, Circle } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
  const n = study.notification;
  // Уведомление появилось на глазах (врач только что принял решение) — подсвечиваем панель
  const [sentNow] = useState(!n);
  if (!n) return null;

  return (
    <Card className={cn(sentNow && "animate-notify-sent")}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BellRing className="size-5 text-primary" /> Уведомление пациента
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-muted-foreground">Отправлено {fmtDateTime(n.sent_at)}:</span>
          {n.channels.map((c) => (
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
        <p className="rounded-xl bg-background p-3 whitespace-pre-wrap">{n.text}</p>

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
        {!n.patient_action && <div className="text-muted-foreground">Пациент ещё не ответил</div>}
      </CardContent>
    </Card>
  );
}
