"use client";

import { Archive, ChevronDown, ChevronUp, Loader2, Lock, Search } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { NewStudyButton } from "@/components/study/new-study-dialog";
import { AgreementBadge, AIBadge, StatusBadge } from "@/components/study-badges";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import type { StudyListItem, StudyStatus } from "@/lib/api/types";
import { useAuth } from "@/lib/auth";
import { fmtDate, STATUS_LABELS, useLabels } from "@/lib/format";
import { cn } from "@/lib/utils";

type View = "work" | "archive" | "all";
type ArchiveFilter = "all" | StudyStatus;

// В работе — ждут решения врача; решённые уходят в архив
const WORK: StudyStatus[] = ["new", "ai_ready", "ai_failed"];
const ARCHIVE: StudyStatus[] = ["decided", "notified", "completed"];

const ARCHIVE_FILTERS: { value: ArchiveFilter; label: string }[] = [
  { value: "all", label: "Весь архив" },
  { value: "notified", label: "Ждём записи пациента" },
  { value: "completed", label: STATUS_LABELS.completed },
];

const COLUMNS = [
  "Пациент",
  "Исследование",
  "Дата",
  "Статус",
  "Рекомендация AI",
  "Решение врача",
  "Лечащий врач",
];

const isUrgent = (s: StudyListItem) =>
  s.ai?.recommendation === "urgent_hospitalization" && !s.decision;

const PAGE = 5; // сколько строк показывать до «Развернуть»

export default function StudiesPage() {
  return (
    <AppShell roles={["doctor", "chief", "manager"]}>
      {/* useSearchParams (?patient= из календаря) требует Suspense при статической сборке */}
      <Suspense fallback={<Skeleton className="h-96 rounded-3xl" />}>
        <StudiesQueue />
      </Suspense>
    </AppShell>
  );
}

function StudiesQueue() {
  const { user } = useAuth();
  const isDoctor = user?.role === "doctor";

  // Из календаря: ?patient=ФИО — все исследования этого пациента (и в работе, и в архиве)
  const params = useSearchParams();
  const patientParam = params.get("patient") ?? "";
  const [view, setView] = useState<View>(patientParam ? "all" : "work");
  // Пациент из календаря — его исследования у всех врачей, не только у текущего
  const [scope, setScope] = useState<"mine" | "all">(isDoctor && !patientParam ? "mine" : "all");
  const [filter, setFilter] = useState<ArchiveFilter>("all");
  const status =
    view === "all" ? undefined : view === "work" ? WORK : filter === "all" ? ARCHIVE : [filter];
  const { data, isLoading, error } = useStudies(scope, status);
  const label = useLabels();
  const router = useRouter();
  const [query, setQuery] = useState(patientParam);
  const [expanded, setExpanded] = useState(false);
  // Свежие сверху; поиск — по ФИО пациента (любая часть, без учёта регистра)
  const q = query.trim().toLowerCase();
  const found = (data ?? [])
    .filter((s) => !q || s.patient.full_name.toLowerCase().includes(q))
    // AI рекомендует экстренную госпитализацию — наверх; дальше свежие
    .sort(
      (a, b) =>
        Number(isUrgent(b)) - Number(isUrgent(a)) || b.performed_at.localeCompare(a.performed_at),
    );
  const shown = expanded ? found : found.slice(0, PAGE);

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-medium tracking-tight md:text-4xl">
            {view === "archive"
              ? "Архив"
              : view === "all"
                ? "Все исследования"
                : isDoctor && scope === "mine"
                  ? "Мои исследования"
                  : "Все исследования"}
          </h1>
          <p className="text-sm text-muted-foreground">
            {data ? (q ? `найдено ${found.length} из ${data.length}` : `${data.length} шт.`) : " "}
          </p>
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
          <Tabs value={view} onValueChange={(v) => setView(v as View)}>
            <TabsList>
              <TabsTrigger value="work">В работе</TabsTrigger>
              <TabsTrigger value="archive">
                <Archive /> Архив
              </TabsTrigger>
              <TabsTrigger value="all">Все статусы</TabsTrigger>
            </TabsList>
          </Tabs>
          {view === "archive" && (
            <Tabs value={filter} onValueChange={(v) => setFilter(v as ArchiveFilter)}>
              <TabsList>
                {ARCHIVE_FILTERS.map((f) => (
                  <TabsTrigger key={f.value} value={f.value}>
                    {f.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            placeholder="Поиск по пациенту"
            aria-label="Поиск по пациенту"
            className="h-10 pl-9"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        {/* Новое исследование из DICOM SR — врач и главврач (менеджер только смотрит) */}
        {user?.role !== "manager" && <NewStudyButton />}
      </div>

      <div className="overflow-hidden rounded-3xl bg-card px-3 py-2">
        <Table>
          <TableHeader>
            <TableRow>
              {COLUMNS.filter((c) => c !== "Лечащий врач" || scope === "all").map((c) => (
                <TableHead key={c}>{c}</TableHead>
              ))}
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
            {data && found.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                  {q
                    ? `Пациентов «${query.trim()}» не найдено`
                    : view === "work"
                      ? "Все исследования разобраны — решённые в архиве"
                      : view === "all"
                        ? "Исследований нет"
                        : "Архив пуст"}
                </TableCell>
              </TableRow>
            )}
            {shown.map((s) => (
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
                    s.ai_auto ? (
                      <span className="inline-flex items-center gap-1.5 text-muted-foreground">
                        <Loader2 className="size-3.5 animate-spin" /> анализирует…
                      </span>
                    ) : (
                      <span className="text-muted-foreground">не отправлено</span>
                    )
                  ) : s.status === "ai_failed" ? (
                    <span className="text-red-700">AI не отвечает</span>
                  ) : (
                    <span className="text-muted-foreground">без AI</span>
                  )}
                </TableCell>
                <TableCell>
                  {s.decision ? (
                    <div className="grid justify-items-start gap-1">
                      <AgreementBadge accepted={s.decision.accepted_ai} />
                      {s.booking && (
                        <span
                          className={cn(
                            "text-xs",
                            s.booking.booked === s.booking.required
                              ? "text-emerald-700"
                              : "text-muted-foreground",
                          )}
                        >
                          записан {s.booking.booked} из {s.booking.required}
                        </span>
                      )}
                    </div>
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
        {found.length > PAGE && (
          <div className="flex justify-center border-t py-2">
            <Button variant="ghost" size="sm" onClick={() => setExpanded((v) => !v)}>
              {expanded ? <ChevronUp /> : <ChevronDown />}
              {expanded ? "Свернуть" : `Развернуть — ещё ${found.length - PAGE}`}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
