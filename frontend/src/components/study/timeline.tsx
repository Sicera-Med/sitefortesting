"use client";

import { History } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useStudyAudit } from "@/lib/api/hooks";
import { fmtDateTime } from "@/lib/format";

const ACTION_LABELS: Record<string, string> = {
  "study.created": "Исследование создано",
  "ai.analyzed": "Анализ AI",
  "ai.reanalyzed": "Повторный анализ AI",
  "ai.failed": "Ошибка AI",
  "decision.created": "Решение врача",
  "notification.sent": "Уведомление отправлено",
  "notification.read": "Пациент прочитал уведомление",
  "patient.booked": "Пациент записался",
  "patient.declined": "Пациент отказался",
  "appointment.created": "Создана запись",
  "appointment.cancelled": "Запись отменена",
};

/** Таймлайн действий по исследованию (аудит, P1). */
export function Timeline({ studyId }: { studyId: string }) {
  const { data } = useStudyAudit(studyId);
  if (!data?.length) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <History className="size-5 text-primary" /> История
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ol className="relative grid gap-4 border-l pl-5">
          {data.map((e) => (
            <li key={e.id} className="relative text-sm">
              <span className="absolute top-1.5 -left-[25px] size-2.5 rounded-full border-2 border-background bg-primary" />
              <div className="font-medium">{ACTION_LABELS[e.action] ?? e.action}</div>
              <div className="text-xs text-muted-foreground">
                {fmtDateTime(e.at)}
                {` · ${e.actor_name ?? "автоматически"}`}
              </div>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}
