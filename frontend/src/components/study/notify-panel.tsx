"use client";

import { BellRing, CalendarCheck, CalendarX } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { StudyCard } from "@/lib/api/types";
import { CHANNEL_LABELS, fmtDateTime, useLabels } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Уведомление пациента: уходит автоматически после решения во все доступные каналы. */
export function NotifyPanel({ study }: { study: StudyCard }) {
  const label = useLabels();
  const n = study.notification;
  if (!n) return null;

  return (
    <Card>
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

        {study.appointments.map((a) => (
          <div
            key={a.id}
            className={cn(
              "flex items-center gap-2 rounded-lg p-3",
              a.status === "cancelled"
                ? "bg-background text-muted-foreground"
                : "bg-emerald-50 text-emerald-900",
            )}
          >
            <CalendarCheck className="size-4 shrink-0" />
            <span className={cn(a.status === "cancelled" && "line-through")}>
              Пациент записался: {a.doctor.full_name}
              {a.doctor.specialty && ` (${label("specialists", a.doctor.specialty)})`},{" "}
              {fmtDateTime(a.scheduled_for)}
            </span>
            {a.status === "cancelled" && <span className="text-xs">отменена</span>}
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
