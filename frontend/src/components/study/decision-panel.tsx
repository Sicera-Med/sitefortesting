"use client";

import { Bot, Check, ClipboardCheck, Loader2, X } from "lucide-react";
import { useState } from "react";

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

function toggle<T>(list: T[], item: T): T[] {
  return list.includes(item) ? list.filter((x) => x !== item) : [...list, item];
}

function DecisionForm({ study }: { study: StudyCard }) {
  const ai = study.ai;
  const aiSpecialists = ai?.details.specialists ?? [];
  const aiResearch = ai?.details.research_types ?? [];
  const dicts = useDictionaries();
  const decide = useDecide(study.id);
  // Без ответа AI ничего не предвыбрано — врач решает сам
  const [types, setTypes] = useState<RecommendationType[]>(ai ? [ai.recommendation] : []);
  const [specialists, setSpecialists] = useState<string[]>(aiSpecialists);
  const [research, setResearch] = useState<string[]>(aiResearch);
  const [comment, setComment] = useState("");

  const score = (t: RecommendationType) => ai?.ranked_options.find((o) => o.type === t)?.score;
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
            {RECOMMENDATION_TYPES.map((t) => (
              <CheckRow
                key={t}
                checked={has(t)}
                onChange={() => setTypes((cur) => toggle(cur, t))}
                label={RECOMMENDATION_LABELS[t]}
                ai={ai?.recommendation === t}
                note={score(t) != null ? pct(score(t)) : undefined}
                className="p-3"
              />
            ))}
          </div>

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
              aiCodes={aiSpecialists}
              onToggle={(c) => setSpecialists((cur) => toggle(cur, c))}
            />
          )}
          {has("additional_research") && (
            <CodeGrid
              title="Исследования и анализы"
              items={dicts.data?.research_types ?? []}
              selected={research}
              aiCodes={aiResearch}
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
                  {study.status === "new"
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

function CheckRow({
  checked,
  onChange,
  label,
  ai,
  note,
  className,
}: {
  checked: boolean;
  onChange: () => void;
  label: string;
  ai?: boolean;
  note?: string;
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
      <span className="flex-1">{label}</span>
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
  onToggle,
}: {
  title: string;
  items: DictItem[];
  selected: string[];
  aiCodes: string[];
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
            {aiText && ` — ${aiText}`} ({pct(decision.ai_confidence)})
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
