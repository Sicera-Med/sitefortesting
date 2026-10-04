"use client";

import { ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";

import { AppShell } from "@/components/app-shell";
import { ConfusionMatrix, RateRow, StatTile, Tip } from "@/components/dashboard/charts";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { errorMessage } from "@/lib/api/client";
import { useDashboard } from "@/lib/api/hooks";
import type { Dashboard, RecommendationType, StudyStatus } from "@/lib/api/types";
import { pct, RECOMMENDATION_LABELS, STATUS_LABELS, useLabels } from "@/lib/format";
import { cn } from "@/lib/utils";

export default function DashboardPage() {
  return (
    <AppShell roles={["manager"]}>
      <DashboardView />
    </AppShell>
  );
}

function Section({
  title,
  note,
  className,
  children,
}: {
  title: React.ReactNode;
  note?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={cn("grid content-start gap-5 rounded-3xl bg-card p-6", className)}>
      <div>
        <h2 className="text-xl font-medium">{title}</h2>
        {note && <p className="mt-1 text-sm text-muted-foreground">{note}</p>}
      </div>
      {children}
    </section>
  );
}

function seconds(ms: number | null) {
  return ms == null ? "—" : `${(ms / 1000).toFixed(1).replace(".", ",")} с`;
}

function DashboardView() {
  const { data, isLoading, error, isFetching } = useDashboard();

  if (isLoading)
    return (
      <div className="grid gap-4">
        <Skeleton className="h-12 w-72" />
        <div className="grid gap-4 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-40 rounded-3xl" />
          ))}
        </div>
        <Skeleton className="h-80 rounded-3xl" />
      </div>
    );
  if (error || !data)
    return (
      <Alert variant="destructive">
        <AlertDescription>{errorMessage(error)}</AlertDescription>
      </Alert>
    );

  // Повторная загрузка — держим прежние данные, без скелетона
  return (
    <div className={cn("grid gap-6 transition-opacity", isFetching && "opacity-80")}>
      <div>
        <h1 className="text-3xl font-medium tracking-tight md:text-4xl">
          <span className="text-muted-foreground">Врачи и</span> AI
        </h1>
        <p className="mt-1 text-muted-foreground">
          Насколько решения врачей совпадают с рекомендациями модели
        </p>
      </div>
      <Kpis data={data} />
      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Matrix data={data} />
        <Doctors data={data} />
      </div>
      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Funnel data={data} />
        <Statuses data={data} />
      </div>
    </div>
  );
}

function Kpis({ data }: { data: Dashboard }) {
  const { agreement, details_agreement: details, summary, latency } = data;
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-[2fr_1fr_1fr]">
      {/* Согласие и полное совпадение — одна плитка: второе уточняет первое */}
      <StatTile
        hero
        label="Врач согласился с AI"
        value={pct(agreement.rate)}
        note={
          <>
            {agreement.agreed} из {agreement.total} решений с рекомендацией AI
            {details.total > 0 && (
              <>
                {" · "}
                <span className="text-foreground">
                  полностью, со специалистом и исследованиями, — {pct(details.rate)}
                </span>{" "}
                ({details.agreed} из {details.total})
              </>
            )}
          </>
        }
        className="md:col-span-2 xl:col-span-1"
      />
      <StatTile
        label="Время ответа модели"
        value={seconds(latency.avg_ms)}
        note={`в среднем · p95 ${seconds(latency.p95_ms)} · ${latency.count} запусков`}
      />
      <StatTile
        label="Сбои AI-сервиса"
        value={String(summary.ai_failures)}
        note={`успешных ответов: ${summary.ai_runs} · решений без AI: ${summary.decisions_without_ai}`}
      />
    </div>
  );
}

function Matrix({ data }: { data: Dashboard }) {
  const { labels, matrix } = data.confusion_matrix;
  return (
    <Section
      title="Что рекомендовал AI и что выбрал врач"
      note="Строки — рекомендация AI, столбцы — что выбрал врач (решение с несколькими направлениями попадает в каждый столбец). На диагонали — согласие."
    >
      <ConfusionMatrix
        labels={labels}
        matrix={matrix}
        labelOf={(c) => RECOMMENDATION_LABELS[c as RecommendationType] ?? c}
      />
    </Section>
  );
}

const TOP_DOCTORS = 5;

function Doctors({ data }: { data: Dashboard }) {
  const label = useLabels();
  const [all, setAll] = useState(false);
  // Backend отдаёт врачей по убыванию согласия с AI
  const rows = all ? data.by_doctor : data.by_doctor.slice(0, TOP_DOCTORS);
  return (
    <Section
      title="Согласие с AI по врачам"
      note="Лидеры сверху. «Полностью» — совпали и специалист, и исследования."
    >
      {data.by_doctor.length ? (
        <div className="grid gap-5">
          {rows.map((d, i) => (
            <RateRow
              key={d.doctor_id}
              label={
                <span>
                  <span className="mr-2 text-muted-foreground tabular-nums">{i + 1}.</span>
                  {d.full_name}
                </span>
              }
              sub={`${label("specialists", d.specialty)} · решений: ${d.decisions}${
                d.details_total ? ` · полностью ${pct(d.details_rate)}` : ""
              }`}
              rate={d}
            />
          ))}
          {data.by_doctor.length > TOP_DOCTORS && (
            <Button
              variant="ghost"
              size="sm"
              className="justify-self-center"
              onClick={() => setAll((v) => !v)}
            >
              {all ? <ChevronUp /> : <ChevronDown />}
              {all ? "Только лидеры" : `Показать всех врачей (${data.by_doctor.length})`}
            </Button>
          )}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">Решений пока нет</p>
      )}
    </Section>
  );
}

const FUNNEL_SCOPES = ["all", "repeat_appointment", "specialist_consult", "additional_research"];

/** Воронка после уведомления: от отправки до записи по всем направлениям. */
function Funnel({ data }: { data: Dashboard }) {
  const [scope, setScope] = useState("all");
  const row = data.funnel.find((r) => r.scope === scope);
  const steps = row
    ? [
        { label: "Уведомление отправлено", n: row.sent },
        { label: "Прочитали", n: row.read },
        { label: "Записались хотя бы по одному направлению", n: row.booked_any },
        { label: "Записались по всем направлениям", n: row.booked_all },
      ]
    : [];
  return (
    <Section
      title="Что делают пациенты после уведомления"
      note="Доля — от отправленных уведомлений, по которым нужно записаться"
    >
      <Tabs value={scope} onValueChange={(v) => setScope(v as string)}>
        <TabsList className="flex-wrap">
          {FUNNEL_SCOPES.map((s) => (
            <TabsTrigger key={s} value={s}>
              {s === "all" ? "Все" : RECOMMENDATION_LABELS[s as RecommendationType]}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      {!row || !row.sent ? (
        <p className="text-sm text-muted-foreground">Уведомлений пока нет</p>
      ) : (
        <div className="grid gap-3">
          {steps.map((step, i) => {
            const share = step.n / row.sent;
            return (
              <Tip
                key={step.label}
                content={`${step.n} из ${row.sent} · ${pct(share, 1)}`}
                className="grid gap-1.5 rounded-xl focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <span>
                    <span className="mr-2 text-muted-foreground tabular-nums">{i + 1}</span>
                    {step.label}
                  </span>
                  <span>
                    <span className="text-xl font-medium tabular-nums">{step.n}</span>
                    <span className="ml-2 text-xs text-muted-foreground tabular-nums">
                      {pct(share)}
                    </span>
                  </span>
                </div>
                {/* Воронка: каждая ступень — доля от отправленных */}
                <div className="h-8 w-full overflow-hidden rounded-lg bg-accent">
                  <div
                    className="h-full rounded-lg bg-primary transition-[width]"
                    style={{
                      width: `${Math.max(share * 100, step.n ? 2 : 0)}%`,
                      opacity: 1 - i * 0.15,
                    }}
                  />
                </div>
              </Tip>
            );
          })}
          <div className="flex items-center justify-between rounded-xl bg-background px-3 py-2 text-sm">
            <span className="text-muted-foreground">Отказались от записи</span>
            <span>
              <span className="font-medium tabular-nums">{row.declined}</span>
              <span className="ml-2 text-xs text-muted-foreground tabular-nums">
                {pct(row.declined / row.sent)}
              </span>
            </span>
          </div>
        </div>
      )}
    </Section>
  );
}

function Statuses({ data }: { data: Dashboard }) {
  const { studies_by_status: byStatus, studies_total: total } = data.summary;
  // «Решение принято» проскакивает мгновенно (уведомление уходит сразу) — нули не показываем
  const rows = (Object.keys(STATUS_LABELS) as StudyStatus[])
    .map((s) => ({ status: s, n: byStatus[s] ?? 0 }))
    .filter((r) => r.n > 0);
  const max = Math.max(1, ...rows.map((r) => r.n));
  return (
    <Section title="Исследования" note={`Всего ${total}`}>
      <div className="grid gap-3">
        {rows.map((r) => (
          <Tip
            key={r.status}
            content={`${STATUS_LABELS[r.status]}: ${r.n} из ${total}`}
            className="grid grid-cols-[9rem_1fr_2rem] items-center gap-3 rounded-lg text-sm focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <span className="text-muted-foreground">{STATUS_LABELS[r.status]}</span>
            <div className="h-3 overflow-hidden rounded-r-[4px] bg-transparent">
              <div
                className="h-full rounded-r-[4px] bg-primary"
                style={{ width: `${(r.n / max) * 100}%` }}
              />
            </div>
            <span className="text-right tabular-nums">{r.n}</span>
          </Tip>
        ))}
      </div>
    </Section>
  );
}
