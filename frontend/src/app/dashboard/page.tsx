"use client";

import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { ConfusionMatrix, RateRow, StatTile, Tip } from "@/components/dashboard/charts";
import { AgreementBadge } from "@/components/study-badges";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { errorMessage } from "@/lib/api/client";
import { useDashboard } from "@/lib/api/hooks";
import type { Dashboard, RecommendationType, StudyStatus } from "@/lib/api/types";
import { fmtDateTime, pct, RECOMMENDATION_LABELS, STATUS_LABELS, useLabels } from "@/lib/format";
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
      <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
        <ByConfidence data={data} />
        <Matrix data={data} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2 xl:grid-cols-3">
        <Doctors data={data} />
        <PatientResponse data={data} />
        <Statuses data={data} />
      </div>
      <RecentDecisions data={data} />
    </div>
  );
}

function Kpis({ data }: { data: Dashboard }) {
  const { agreement, details_agreement: details, summary, latency } = data;
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <StatTile
        hero
        label="Врач согласился с AI"
        value={pct(agreement.rate)}
        note={`${agreement.agreed} из ${agreement.total} решений с рекомендацией AI`}
        className="md:col-span-2 xl:col-span-1 xl:row-span-1"
      />
      <StatTile
        label="Совпали детали — специалист и исследования"
        value={pct(details.rate)}
        note={`${details.agreed} из ${details.total}, где тип совпал и AI предложил детали`}
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

function ByConfidence({ data }: { data: Dashboard }) {
  const { threshold, high, low } = data.agreement_by_confidence;
  const t = pct(threshold);
  const insight =
    high.rate != null && low.rate != null && high.total && low.total
      ? high.rate > low.rate
        ? "Когда модель уверена, врачи соглашаются с ней заметно чаще."
        : "Уверенность модели пока не влияет на согласие врачей."
      : null;
  return (
    <Section
      title="Согласие и уверенность модели"
      note={insight ?? `Порог высокой уверенности — ${t}`}
    >
      <div className="grid gap-6">
        <RateRow label={`Уверенность ≥ ${t}`} sub="модель уверена" rate={high} />
        <RateRow label={`Уверенность < ${t}`} sub="модель сомневается" rate={low} />
      </div>
    </Section>
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

function Doctors({ data }: { data: Dashboard }) {
  const label = useLabels();
  return (
    <Section title="По врачам" note="Доля решений, совпавших с рекомендацией AI">
      {data.by_doctor.length ? (
        <div className="grid gap-5">
          {data.by_doctor.map((d) => (
            <RateRow
              key={d.doctor_id}
              label={d.full_name}
              sub={`${label("specialists", d.specialty)} · решений: ${d.decisions}`}
              rate={d}
            />
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">Решений пока нет</p>
      )}
    </Section>
  );
}

function PatientResponse({ data }: { data: Dashboard }) {
  return (
    <Section title="Пациенты после уведомления" note="Доля записавшихся на приём">
      <div className="grid gap-5">
        {data.notifications.map((n) => (
          <RateRow
            key={n.recommendation}
            label={RECOMMENDATION_LABELS[n.recommendation as RecommendationType]}
            sub={`отправлено ${n.sent} · отказались ${n.declined} · ждут ответа ${n.pending}`}
            rate={{ agreed: n.booked, total: n.sent, rate: n.sent ? n.booked_rate : null }}
            unit="пациентов"
          />
        ))}
      </div>
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

function RecentDecisions({ data }: { data: Dashboard }) {
  const label = useLabels();
  return (
    <Section title="Последние решения">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Пациент</TableHead>
            <TableHead>AI</TableHead>
            <TableHead>Врач</TableHead>
            <TableHead>Совпадение</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.recent_decisions.map((d) => (
            <TableRow key={d.decision_id}>
              <TableCell>
                <Link href={`/studies/${d.study_id}`} className="font-medium hover:text-primary">
                  {d.patient_name}
                </Link>
                <div className="text-xs text-muted-foreground">
                  {label("study_types", d.study_type)} · {fmtDateTime(d.created_at)}
                </div>
              </TableCell>
              <TableCell>
                {d.ai_recommendation ? (
                  <>
                    <div>{RECOMMENDATION_LABELS[d.ai_recommendation as RecommendationType]}</div>
                    <div className="text-xs text-muted-foreground tabular-nums">
                      уверенность {pct(d.ai_confidence)}
                    </div>
                  </>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell>
                <div>
                  {d.chosen_types
                    .map((t) => RECOMMENDATION_LABELS[t as RecommendationType])
                    .join(" + ")}
                </div>
                <div className="text-xs text-muted-foreground">{d.doctor_name}</div>
              </TableCell>
              <TableCell>
                <div className="flex flex-wrap gap-1">
                  <AgreementBadge accepted={d.accepted_ai} />
                  {d.details_match === false && (
                    <Badge className="bg-amber-100 text-amber-800">детали отличаются</Badge>
                  )}
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Section>
  );
}
