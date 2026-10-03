"use client";

import { ArrowLeft, Lock } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { AIPanel } from "@/components/study/ai-panel";
import { DecisionPanel } from "@/components/study/decision-panel";
import { NotifyPanel } from "@/components/study/notify-panel";
import { Timeline } from "@/components/study/timeline";
import { StatusBadge } from "@/components/study-badges";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api/client";
import { useStudy } from "@/lib/api/hooks";
import type { StudyStatus } from "@/lib/api/types";
import { useAuth } from "@/lib/auth";
import { fmtDate, useLabels } from "@/lib/format";

const ANALYZABLE: StudyStatus[] = ["new", "ai_ready", "ai_failed"];

export default function StudyPage() {
  return (
    <AppShell roles={["doctor", "head"]}>
      <StudyView />
    </AppShell>
  );
}

function StudyView() {
  const { id } = useParams<{ id: string }>();
  const { data: study, isLoading, error } = useStudy(id);
  const { user } = useAuth();
  const label = useLabels();

  if (isLoading)
    return (
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-96" />
        <Skeleton className="h-96" />
      </div>
    );
  if (error || !study)
    return (
      <Alert variant="destructive">
        <AlertDescription>{errorMessage(error)}</AlertDescription>
      </Alert>
    );

  // Анализ идёт сам; вручную можно лишь загрузить ответ AI (запасной путь §6.5), пока нет решения
  const canUpload = (study.can_act || user?.role === "head") && ANALYZABLE.includes(study.status);

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link
          href="/studies"
          className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
        >
          <ArrowLeft className="size-4" /> К списку
        </Link>
      </div>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-3xl font-medium tracking-tight md:text-4xl">
            {study.patient.full_name}
          </h1>
          <p className="text-sm text-muted-foreground">
            {study.patient.age} лет, {study.patient.sex === "m" ? "мужской" : "женский"} ·{" "}
            {label("study_types", study.study_type)}, {label("body_regions", study.body_region)} ·{" "}
            {fmtDate(study.performed_at)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {!study.can_act && user?.role === "doctor" && (
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <Lock className="size-3" /> Лечащий врач: {study.doctor.full_name}
            </span>
          )}
          <StatusBadge status={study.status} />
        </div>
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-[1fr_1fr]">
        <Card className="lg:sticky lg:top-20">
          <CardHeader>
            <CardTitle>Заключение</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-[70vh] overflow-y-auto text-sm leading-relaxed whitespace-pre-wrap">
              {study.report_text}
            </div>
          </CardContent>
        </Card>

        <div className="grid gap-4">
          <AIPanel study={study} canUpload={canUpload} />
          <DecisionPanel study={study} />
          <NotifyPanel study={study} />
          <Timeline studyId={study.id} />
        </div>
      </div>
    </div>
  );
}
