"use client";

import { CalendarPlus, CircleCheck, Clock, FileText, Siren, XCircle } from "lucide-react";
import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api/client";
import { useMyStudies } from "@/lib/api/hooks";
import type { PatientStudy } from "@/lib/api/types";
import { fmtDate, RECOMMENDATION_LABELS, useLabels } from "@/lib/format";
import { cn } from "@/lib/utils";

export default function PatientStudiesPage() {
  return (
    <AppShell roles={["patient"]}>
      <StudiesView />
    </AppShell>
  );
}

/** Понятный пациенту статус исследования. */
function state(s: PatientStudy) {
  if (!s.recommendations)
    return {
      tone: "muted" as const,
      icon: Clock,
      title: "Результат у врача",
      text: "Врач изучает результат — мы сообщим, когда будет решение.",
    };
  if (s.recommendations.includes("urgent_hospitalization"))
    return {
      tone: "urgent" as const,
      icon: Siren,
      title: "Срочно обратитесь в стационар",
      text: "Врач рекомендует экстренную госпитализацию. При ухудшении — 103.",
    };
  if (s.recommendations.includes("no_pathology"))
    return {
      tone: "ok" as const,
      icon: CircleCheck,
      title: "Патологии не выявлено",
      text: "Записываться на приём не нужно.",
    };
  if (s.patient_action === "declined")
    return {
      tone: "muted" as const,
      icon: XCircle,
      title: "Вы отказались от записи",
      text: "Записаться к врачу можно в разделе «Рекомендации».",
    };
  if (s.booking && s.booking.booked === s.booking.required)
    return {
      tone: "ok" as const,
      icon: CircleCheck,
      title: "Вы записаны",
      text: "По всем направлениям врача.",
    };
  return {
    tone: "primary" as const,
    icon: CalendarPlus,
    title: "Врач дал рекомендации — запишитесь",
    text: s.booking ? `Записано ${s.booking.booked} из ${s.booking.required}` : "",
  };
}

const TONES = {
  urgent: "bg-red-600 text-white",
  primary: "bg-primary/10 text-primary",
  ok: "bg-emerald-100 text-emerald-800",
  muted: "bg-background text-muted-foreground",
} as const;

function StudiesView() {
  const { data, isLoading, error } = useMyStudies();
  const label = useLabels();

  return (
    <div className="mx-auto grid max-w-4xl gap-6">
      <div>
        <h1 className="text-3xl font-medium tracking-tight md:text-4xl">Мои исследования</h1>
        <p className="text-sm text-muted-foreground">
          Все ваши исследования и что по ним решил врач
        </p>
      </div>

      {isLoading && <Skeleton className="h-48 rounded-3xl" />}
      {error && <p className="text-sm text-destructive">{errorMessage(error)}</p>}
      {data && !data.length && (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            Исследований пока нет
          </CardContent>
        </Card>
      )}

      <div className="grid gap-3">
        {data?.map((s) => {
          const st = state(s);
          const Icon = st.icon;
          return (
            <Card key={s.id}>
              <CardContent className="flex flex-wrap items-center gap-4">
                <span
                  className={cn(
                    "grid size-12 shrink-0 place-items-center rounded-2xl",
                    TONES[st.tone],
                  )}
                >
                  <Icon className="size-6" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">
                      {label("study_types", s.study_type)},{" "}
                      {label("body_regions", s.body_region).toLowerCase()}
                    </span>
                    <span className="text-sm text-muted-foreground">
                      от {fmtDate(s.performed_at)}
                    </span>
                  </div>
                  <div
                    className={cn("text-sm font-medium", st.tone === "ok" && "text-emerald-700")}
                  >
                    {st.title}
                  </div>
                  <div className="text-sm text-muted-foreground">
                    {st.text}
                    {s.recommendations &&
                      !s.recommendations.includes("no_pathology") &&
                      ` · ${s.recommendations.map((r) => RECOMMENDATION_LABELS[r]).join(", ")}`}
                  </div>
                  <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                    <FileText className="size-3.5" /> лечащий врач {s.treating_doctor.full_name}
                  </div>
                </div>
                {s.notification_id && (
                  <Button
                    variant={st.tone === "primary" ? "default" : "outline"}
                    size={st.tone === "primary" ? "lg" : "default"}
                    render={<Link href={`/patient#n-${s.notification_id}`} />}
                    nativeButton={false}
                  >
                    {st.tone === "primary" ? "Записаться" : "Подробнее"}
                  </Button>
                )}
                {!s.notification_id && <Badge variant="secondary">ждём решение</Badge>}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
