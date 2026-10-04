"use client";

import { ArrowLeft, Loader2, Lock } from "lucide-react";
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
import { useDoctors, useReassign, useStudy } from "@/lib/api/hooks";
import type { StudyCard, StudyStatus } from "@/lib/api/types";
import { useAuth } from "@/lib/auth";
import { fmtDate, useLabels } from "@/lib/format";

const ANALYZABLE: StudyStatus[] = ["new", "ai_ready", "ai_failed"];

export default function StudyPage() {
  return (
    <AppShell roles={["doctor", "chief", "manager"]}>
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
          {user?.role === "chief" && ANALYZABLE.includes(study.status) && (
            <ReassignControl study={study} />
          )}
          {!study.can_act && user?.role !== "chief" && (
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <Lock className="size-3" /> Лечащий врач: {study.doctor.full_name}
            </span>
          )}
          <StatusBadge status={study.status} />
        </div>
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-[1fr_1fr]">
        {/* Слева — рекомендация AI и заключение, справа — что делает врач */}
        <div className="grid gap-4">
          <AIPanel study={study} />
          <SRProtocol study={study} />
        </div>

        <div className="grid gap-4">
          <DecisionPanel study={study} />
          <NotifyPanel study={study} />
          <Timeline studyId={study.id} />
        </div>
      </div>
    </div>
  );
}

/** Главврач передаёт пациента другому врачу, пока решение не принято. */
function ReassignControl({ study }: { study: StudyCard }) {
  const doctors = useDoctors();
  const reassign = useReassign(study.id);
  const label = useLabels();
  return (
    <span className="inline-flex flex-wrap items-center gap-2 text-sm">
      <span className="text-muted-foreground">Лечащий врач:</span>
      <select
        className="h-8 rounded-md border border-input bg-transparent px-2 text-sm"
        value={study.doctor.id}
        disabled={reassign.isPending}
        onChange={(e) => reassign.mutate(e.target.value)}
      >
        {(doctors.data ?? [study.doctor]).map((d) => (
          <option key={d.id} value={d.id}>
            {d.full_name} — {label("specialists", d.specialty)}
          </option>
        ))}
      </select>
      {reassign.isPending && <Loader2 className="size-4 animate-spin" />}
      {reassign.isError && (
        <span className="text-xs text-destructive">{errorMessage(reassign.error)}</span>
      )}
    </span>
  );
}

/** Протокол как он пришёл: раздел «Описание» DICOM SR (поля БФТ) и заключение рентгенолога. */
function SRProtocol({ study }: { study: StudyCard }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Протокол (DICOM SR)</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 text-sm">
        {study.sr_fields.length > 0 ? (
          <dl className="grid max-h-[50vh] gap-x-4 gap-y-2 overflow-y-auto sm:grid-cols-[minmax(9rem,14rem)_1fr]">
            {study.sr_fields.map((f, i) => (
              <div key={i} className="contents">
                <dt className="text-muted-foreground">{f.name}</dt>
                <dd className="font-medium">{f.value}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="text-muted-foreground">Описания в протоколе нет — только заключение.</p>
        )}
        <div className="rounded-xl bg-background p-3">
          <div className="text-xs font-medium text-muted-foreground">Заключение рентгенолога</div>
          <p className="mt-1">{study.conclusion ?? "Заключения в протоколе нет"}</p>
        </div>
      </CardContent>
    </Card>
  );
}
