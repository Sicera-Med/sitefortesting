"use client";

import { Loader2, Lock } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AppShell } from "@/components/app-shell";
import { AgreementBadge, AIBadge, StatusBadge } from "@/components/study-badges";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { errorMessage } from "@/lib/api/client";
import { useStudies } from "@/lib/api/hooks";
import type { StudyStatus } from "@/lib/api/types";
import { useAuth } from "@/lib/auth";
import { fmtDate, STATUS_LABELS, useLabels } from "@/lib/format";
import { cn } from "@/lib/utils";

type Filter = "all" | "todo" | StudyStatus;

// «К работе» — то, где врачу нужно что-то сделать
const TODO: StudyStatus[] = ["new", "ai_ready", "ai_failed", "decided"];

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "Все" },
  { value: "todo", label: "К работе" },
  { value: "notified", label: STATUS_LABELS.notified },
  { value: "completed", label: STATUS_LABELS.completed },
];

export default function StudiesPage() {
  return (
    <AppShell roles={["doctor", "head"]}>
      <StudiesQueue />
    </AppShell>
  );
}

function StudiesQueue() {
  const { user } = useAuth();
  const isDoctor = user?.role === "doctor";
  const [scope, setScope] = useState<"mine" | "all">(isDoctor ? "mine" : "all");
  const [filter, setFilter] = useState<Filter>("all");
  const status = filter === "all" ? undefined : filter === "todo" ? TODO : [filter as StudyStatus];
  const { data, isLoading, error } = useStudies(scope, status);
  const label = useLabels();
  const router = useRouter();

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-medium tracking-tight md:text-4xl">
            {isDoctor && scope === "mine" ? "Мои исследования" : "Все исследования"}
          </h1>
          <p className="text-sm text-muted-foreground">{data ? `${data.length} шт.` : " "}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {isDoctor && (
            <Tabs value={scope} onValueChange={(v) => setScope(v as "mine" | "all")}>
              <TabsList>
                <TabsTrigger value="mine">Мои</TabsTrigger>
                <TabsTrigger value="all">Все</TabsTrigger>
              </TabsList>
            </Tabs>
          )}
          <Tabs value={filter} onValueChange={(v) => setFilter(v as Filter)}>
            <TabsList>
              {FILTERS.map((f) => (
                <TabsTrigger key={f.value} value={f.value}>
                  {f.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>
      </div>

      <div className="overflow-hidden rounded-3xl bg-card px-3 py-2">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Пациент</TableHead>
              <TableHead>Исследование</TableHead>
              <TableHead>Дата</TableHead>
              <TableHead>Статус</TableHead>
              <TableHead>Рекомендация AI</TableHead>
              <TableHead>Решение врача</TableHead>
              {scope === "all" && <TableHead>Лечащий врач</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading &&
              Array.from({ length: 6 }).map((_, i) => (
                <TableRow key={i}>
                  <TableCell colSpan={7}>
                    <Skeleton className="h-6 w-full" />
                  </TableCell>
                </TableRow>
              ))}
            {error && (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-destructive">
                  {errorMessage(error)}
                </TableCell>
              </TableRow>
            )}
            {data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                  Нет исследований
                </TableCell>
              </TableRow>
            )}
            {data?.map((s) => (
              <TableRow
                key={s.id}
                className={cn(
                  "cursor-pointer",
                  isDoctor && s.doctor.id !== user?.id && "opacity-75",
                )}
                onClick={() => router.push(`/studies/${s.id}`)}
              >
                <TableCell>
                  <div className="font-medium">{s.patient.full_name}</div>
                  <div className="text-xs text-muted-foreground">
                    {s.patient.age} лет, {s.patient.sex === "m" ? "м" : "ж"}
                  </div>
                </TableCell>
                <TableCell>
                  <div>{label("study_types", s.study_type)}</div>
                  <div className="text-xs text-muted-foreground">
                    {label("body_regions", s.body_region)}
                  </div>
                </TableCell>
                <TableCell className="tabular-nums">{fmtDate(s.performed_at)}</TableCell>
                <TableCell>
                  <StatusBadge status={s.status} />
                </TableCell>
                <TableCell>
                  {s.ai ? (
                    <AIBadge recommendation={s.ai.recommendation} confidence={s.ai.confidence} />
                  ) : s.status === "new" ? (
                    <span className="inline-flex items-center gap-1.5 text-muted-foreground">
                      <Loader2 className="size-3.5 animate-spin" /> анализирует…
                    </span>
                  ) : s.status === "ai_failed" ? (
                    <span className="text-red-700">AI не отвечает</span>
                  ) : (
                    <span className="text-muted-foreground">без AI</span>
                  )}
                </TableCell>
                <TableCell>
                  {s.decision ? (
                    <AgreementBadge accepted={s.decision.accepted_ai} />
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                {scope === "all" && (
                  <TableCell>
                    <span className="inline-flex items-center gap-1.5">
                      {isDoctor && s.doctor.id !== user?.id && (
                        <Lock className="size-3 text-muted-foreground" />
                      )}
                      {s.doctor.full_name}
                    </span>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
