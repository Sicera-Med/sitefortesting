"use client";

import { Bot, Check, ClipboardCheck, Loader2, ShieldCheck, X } from "lucide-react";
import { useState } from "react";

import { SourceLinks } from "@/components/study/source-links";
import { AgreementBadge } from "@/components/study-badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage } from "@/lib/api/client";
import { useDecide, useDictionaries } from "@/lib/api/hooks";
import type {
  Decision,
  DecisionDetails,
  DictItem,
  RecommendationType,
  SourceRef,
  StudyCard,
} from "@/lib/api/types";
import {
  fmtDateTime,
  pct,
  RECOMMENDATION_LABELS,
  RECOMMENDATION_TYPES,
  useDecisionItems,
  useDetailsText,
} from "@/lib/format";
import { cn } from "@/lib/utils";

/** Форма решения (нет решения) или итог (решение есть). */
export function DecisionPanel({ study }: { study: StudyCard }) {
  if (study.decision) return <DecisionSummary decision={study.decision} />;
  if (!study.can_act) return null;
  // key: когда придёт ответ AI, форма заново предвыберет его варианты
  return <DecisionForm key={study.ai?.id ?? "no-ai"} study={study} />;
}

function sameSet(a: string[], b: string[]) {
  return a.length === b.length && a.every((x) => b.includes(x));
}

/** «Патологии не выявлено» — только отдельно: выбор снимает остальные и наоборот. */
// Исходы, которые не сочетаются с направлениями (как EXCLUSIVE_TYPES на backend)
const EXCLUSIVE: RecommendationType[] = ["urgent_hospitalization", "no_pathology"];

/** Исход выбирается только отдельно: выбор снимает остальные галочки и наоборот. */
function pick(cur: RecommendationType[], t: RecommendationType): RecommendationType[] {
  if (EXCLUSIVE.includes(t)) return cur.includes(t) ? [] : [t];
  return toggle(
    cur.filter((x) => !EXCLUSIVE.includes(x)),
    t,
  );
}

function toggle<T>(list: T[], item: T): T[] {
  return list.includes(item) ? list.filter((x) => x !== item) : [...list, item];
}

function DecisionForm({ study }: { study: StudyCard }) {
  const ai = study.ai;
  const aiSpecialists = ai?.details.specialists ?? [];
  const aiResearch = ai?.details.research_types ?? [];
  // Пометка «AI» и источник — у кодов из всех вариантов модели, не только основного
  const aiItems = new Map(
    (ai?.options ?? []).flatMap((o) => o.items.map((i) => [`${o.type}:${i.code}`, i] as const)),
  );
  const aiSpecialistCodes = [
    ...new Set([...aiSpecialists, ...keysOf(aiItems, "specialist_consult")]),
  ];
  const aiResearchCodes = [...new Set([...aiResearch, ...keysOf(aiItems, "additional_research")])];
  const dicts = useDictionaries();
  const decide = useDecide(study.id);
  // Без ответа AI ничего не предвыбрано — врач решает сам
  const [types, setTypes] = useState<RecommendationType[]>(ai ? [ai.recommendation] : []);
  const [specialists, setSpecialists] = useState<string[]>(aiSpecialists);
  const [research, setResearch] = useState<string[]>(aiResearch);
  const [comment, setComment] = useState("");

  // Оценка варианта — только если модель её дала (у модели коллег оценок нет)
  const note = (t: RecommendationType) => {
    const score = ai?.ranked_options.find((o) => o.type === t)?.score;
    return score != null ? pct(score) : undefined;
  };
  const has = (t: RecommendationType) => types.includes(t);

  const details: DecisionDetails = {};
  if (has("specialist_consult")) details.specialists = specialists;
  if (has("additional_research")) details.research_types = research;
  const missing =
    types.length === 0
      ? "Выберите хотя бы одно направление"
      : has("specialist_consult") && !specialists.length
        ? "Выберите специалиста"
        : has("additional_research") && !research.length
          ? "Выберите исследование"
          : null;

  // Совпадение с AI: вариант AI среди выбранных; детали — по варианту AI
  const agrees = ai ? has(ai.recommendation) : null;
  let detailsMatch: boolean | null = null;
  if (ai && agrees) {
    if (ai.recommendation === "specialist_consult" && aiSpecialists.length)
      detailsMatch = sameSet(specialists, aiSpecialists);
    if (ai.recommendation === "additional_research" && aiResearch.length)
      detailsMatch = sameSet(research, aiResearch);
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    decide.mutate({ chosen_types: types, details, comment: comment.trim() || null });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ClipboardCheck className="size-5 text-primary" /> Решение врача
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form className="grid gap-5" onSubmit={submit}>
          <div className="grid gap-2">
            <Label>Направления — можно несколько</Label>
            {RECOMMENDATION_TYPES.filter((t) => !EXCLUSIVE.includes(t)).map((t) => (
              <CheckRow
                key={t}
                checked={has(t)}
                onChange={() => setTypes((cur) => pick(cur, t))}
                label={RECOMMENDATION_LABELS[t]}
                ai={ai?.recommendation === t}
                note={note(t)}
                className="p-3"
              />
            ))}
            {/* «Патологии не выявлено» — отдельный исход, а не ещё одно направление */}
            <div className="flex items-center gap-3 py-1 text-xs text-muted-foreground">
              <span className="h-px flex-1 bg-border" /> или{" "}
              <span className="h-px flex-1 bg-border" />
            </div>
            <OutcomeRow
              tone="plain"
              checked={has("urgent_hospitalization")}
              onChange={() => setTypes((cur) => pick(cur, "urgent_hospitalization"))}
              title="Экстренная госпитализация"
              hint="Пациенту — срочное уведомление обратиться в стационар, без записи"
              ai={ai?.recommendation === "urgent_hospitalization"}
            />
            <OutcomeRow
              tone="ok"
              checked={has("no_pathology")}
              onChange={() => setTypes((cur) => pick(cur, "no_pathology"))}
              title="Патологии не выявлено"
              hint="Пациенту не нужно записываться — кейс закроется сразу"
              ai={ai?.recommendation === "no_pathology"}
            />
          </div>

          {has("no_pathology") && (
            <p className="text-sm text-muted-foreground">
              Пациент получит уведомление, что патологии не выявлено и записываться не нужно — кейс
              закроется сразу.
            </p>
          )}
          {has("repeat_appointment") && (
            <p className="text-sm text-muted-foreground">
              Повторный приём: пациент сам выберет удобное время для записи к вам.
            </p>
          )}
          {has("specialist_consult") && (
            <CodeGrid
              title="Специалисты"
              items={dicts.data?.specialists ?? []}
              selected={specialists}
              aiCodes={aiSpecialistCodes}
              sources={(c) => aiItems.get(`specialist_consult:${c}`)?.source_refs}
              onToggle={(c) => setSpecialists((cur) => toggle(cur, c))}
            />
          )}
          {has("additional_research") && (
            <CodeGrid
              title="Исследования и анализы"
              items={dicts.data?.research_types ?? []}
              selected={research}
              aiCodes={aiResearchCodes}
              sources={(c) => aiItems.get(`additional_research:${c}`)?.source_refs}
              onToggle={(c) => setResearch((cur) => toggle(cur, c))}
            />
          )}

          <div className="grid gap-1.5">
            <Label htmlFor="comment">Комментарий</Label>
            <Textarea
              id="comment"
              placeholder="Необязательно"
              maxLength={2000}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
            />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="grid gap-0.5 text-sm">
              {agrees == null ? (
                <span className="text-muted-foreground">
                  {study.status === "new" && study.ai_auto
                    ? "AI ещё анализирует — можно решить и без него"
                    : "Решение без рекомендации AI"}
                </span>
              ) : agrees ? (
                <span className="inline-flex items-center gap-1 text-emerald-700">
                  <Check className="size-4" /> Вариант AI выбран
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-red-700">
                  <X className="size-4" /> Вариант AI не выбран
                </span>
              )}
              {detailsMatch != null && (
                <span
                  className={cn(
                    "inline-flex items-center gap-1 text-xs",
                    detailsMatch ? "text-emerald-700" : "text-amber-700",
                  )}
                >
                  {detailsMatch ? <Check className="size-3.5" /> : <X className="size-3.5" />}
                  {detailsMatch ? "Детали как у AI" : "Детали отличаются от AI"}
                </span>
              )}
              {missing && <span className="text-xs text-muted-foreground">{missing}</span>}
            </div>
            <Button type="submit" disabled={!!missing || decide.isPending}>
              {decide.isPending && <Loader2 className="animate-spin" />}
              Сохранить решение
            </Button>
          </div>
          {decide.isError && (
            <p className="text-sm text-destructive">{errorMessage(decide.error)}</p>
          )}
        </form>
      </CardContent>
    </Card>
  );
}

function AIMark() {
  return (
    <span className="inline-flex items-center gap-1 text-xs text-primary">
      <Bot className="size-3.5" /> AI
    </span>
  );
}

function keysOf(items: Map<string, unknown>, type: string): string[] {
  return [...items.keys()].filter((k) => k.startsWith(`${type}:`)).map((k) => k.split(":")[1]);
}

/** Исход без записи: экстренная госпитализация (обычная строка) или «патологии не выявлено» (зелёный). */
function OutcomeRow({
  tone,
  checked,
  onChange,
  title,
  hint,
  ai,
}: {
  tone: "plain" | "ok";
  checked: boolean;
  onChange: () => void;
  title: string;
  hint: string;
  ai: boolean;
}) {
  const plain = tone === "plain";
  return (
    <label
      className={cn(
        "flex cursor-pointer items-center gap-3 rounded-xl p-3 text-sm transition-colors",
        plain
          ? "border bg-background hover:border-primary/40"
          : "border-2 border-emerald-300 bg-emerald-50 text-emerald-900 hover:border-emerald-500",
        checked && (plain ? "border-primary bg-primary/5" : "border-emerald-600 bg-emerald-100"),
      )}
    >
      <input
        type="checkbox"
        className={cn("size-4", plain ? "accent-primary" : "accent-emerald-600")}
        checked={checked}
        onChange={onChange}
      />
      {!plain && <ShieldCheck className="size-5 shrink-0" />}
      <span className="flex-1">
        <span className="font-medium">{title}</span>
        <span className="block text-xs opacity-80">{hint}</span>
      </span>
      {ai && <AIMark />}
    </label>
  );
}

function CheckRow({
  checked,
  onChange,
  label,
  ai,
  note,
  sources,
  className,
}: {
  checked: boolean;
  onChange: () => void;
  label: string;
  ai?: boolean;
  note?: string;
  sources?: SourceRef[];
  className?: string;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-center gap-2 rounded-xl border bg-background px-3 py-2 text-sm transition-colors hover:border-primary/40",
        checked && "border-primary bg-primary/5 hover:bg-primary/5",
        className,
      )}
    >
      <input
        type="checkbox"
        className="size-4 accent-primary"
        checked={checked}
        onChange={onChange}
      />
      <span className="flex-1">
        {label}
        {sources && sources.length > 0 && <SourceLinks refs={sources} compact className="mt-0.5" />}
      </span>
      {ai && <AIMark />}
      {note && (
        <span className="w-10 text-right text-xs tabular-nums text-muted-foreground">{note}</span>
      )}
    </label>
  );
}

function CodeGrid({
  title,
  items,
  selected,
  aiCodes,
  sources,
  onToggle,
}: {
  title: string;
  items: DictItem[];
  selected: string[];
  aiCodes: string[];
  sources?: (code: string) => SourceRef[] | undefined;
  onToggle: (code: string) => void;
}) {
  return (
    <div className="grid gap-1.5">
      <Label>{title}</Label>
      <div className="grid gap-1.5 sm:grid-cols-2">
        {items.map((i) => (
          <CheckRow
            key={i.code}
            checked={selected.includes(i.code)}
            onChange={() => onToggle(i.code)}
            label={i.label}
            ai={aiCodes.includes(i.code)}
            sources={sources?.(i.code)}
          />
        ))}
      </div>
    </div>
  );
}

function DecisionSummary({ decision }: { decision: Decision }) {
  const items = useDecisionItems()(decision.chosen_types, decision.details);
  const detailsText = useDetailsText();
  const aiText =
    decision.ai_recommendation && decision.ai_details
      ? detailsText(decision.ai_recommendation, decision.ai_details)
      : null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ClipboardCheck className="size-5 text-primary" /> Решение врача
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        <div className="flex flex-wrap gap-1.5">
          <AgreementBadge accepted={decision.accepted_ai} />
          {decision.details_match === true && (
            <Badge className="bg-emerald-100 text-emerald-800">
              <Check /> Детали как у AI
            </Badge>
          )}
          {decision.details_match === false && (
            <Badge className="bg-amber-100 text-amber-800">
              <X /> Детали отличаются
            </Badge>
          )}
        </div>
        <ul className="grid gap-1.5">
          {items.map((i) => (
            <li key={i.type} className="rounded-xl bg-background px-3 py-2">
              <span className="font-medium">{i.label}</span>
              {i.text && <span className="text-muted-foreground"> — {i.text}</span>}
            </li>
          ))}
        </ul>
        {decision.ai_recommendation && (
          <div className="text-muted-foreground">
            AI рекомендовал: {RECOMMENDATION_LABELS[decision.ai_recommendation]}
            {aiText && ` — ${aiText}`}
            {decision.ai_confidence != null && ` (${pct(decision.ai_confidence)})`}
          </div>
        )}
        {decision.comment && (
          <blockquote className="border-l-2 pl-3 text-muted-foreground italic">
            {decision.comment}
          </blockquote>
        )}
        <div className="text-xs text-muted-foreground">{fmtDateTime(decision.created_at)}</div>
      </CardContent>
    </Card>
  );
}
