"use client";

import { AlertTriangle, Bot, Loader2, RotateCw, Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { confidenceTone } from "@/components/study-badges";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { errorMessage } from "@/lib/api/client";
import { AI_SEND_COOLDOWN_MS, aiSendWait, useRetryAI, useStudyAudit } from "@/lib/api/hooks";
import type { Inference, StudyCard } from "@/lib/api/types";
import { fmtDateTime, pct, RECOMMENDATION_LABELS, useLabels } from "@/lib/format";
import { cn } from "@/lib/utils";

const SOURCE_LABELS = {
  mock: "тестовые данные",
  http: "AI-сервис",
  manual: "загружен вручную",
} as const;

/**
 * Сколько ждать до следующей отправки в AI, мс: время из карточки (backend помнит
 * отправку и после обновления страницы) и локальная отметка (до перезагрузки карточки).
 */
function sendWait(study: StudyCard, now: number): number {
  const server = study.ai_send_after ? Date.parse(study.ai_send_after) - now : 0;
  return Math.max(0, server, aiSendWait(study.id, now));
}

/** Панель AI: анализ идёт сам; врач видит результат или честный статус «не отвечает». */
export function AIPanel({ study }: { study: StudyCard }) {
  const audit = useStudyAudit(study.id);
  const retry = useRetryAI(study.id);
  const ai = study.ai;
  // Автоотправка выключена — новое исследование ждёт, пока врач отправит его в AI
  const waiting = study.status === "new" && study.ai_auto;
  const notSent = study.status === "new" && !study.ai_auto;
  const failed = study.status === "ai_failed";
  const decidedWithoutAI = !ai && !waiting && !notSent && !failed;

  // Открыл карточку тот, кто решает по исследованию, — новое заключение уходит в AI само.
  // Один раз за открытие; после сбоя — только кнопкой (каждое открытие тратило бы запрос)
  const sent = useRef(false);
  const { mutate: send } = retry;
  const autoSend = notSent && study.can_act;
  useEffect(() => {
    // Карточку открыли снова (или обновили страницу), а запрос уже уходил в последние 10 с —
    // не повторяем
    if (autoSend && !sent.current && sendWait(study, Date.now()) === 0) {
      sent.current = true;
      send();
    }
  }, [autoSend, send, study]);

  // Обратный отсчёт до следующей разрешённой отправки — кнопка заблокирована
  const [now, setNow] = useState(() => Date.now());
  const cooldown = Math.ceil(sendWait(study, now) / 1000);
  const { isPending } = retry;
  useEffect(() => {
    if (isPending) return;
    const timer = setInterval(() => setNow(Date.now()), 500);
    const stop = setTimeout(() => clearInterval(timer), AI_SEND_COOLDOWN_MS + 1000);
    return () => {
      clearInterval(timer);
      clearTimeout(stop);
    };
  }, [isPending]);
  // До ответа на автоотправку показываем «анализирует», а не «не отправлено»
  const sending = retry.isPending || (autoSend && !retry.isError);
  // Последняя ошибка AI — из аудита (что именно ответил или не ответил сервис)
  const lastError = [...(audit.data ?? [])].reverse().find((e) => e.action === "ai.failed");

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Bot className="size-5 text-primary" /> Рекомендация AI
        </CardTitle>
        {(failed || notSent) && study.can_act && (
          <CardAction>
            <Button
              variant="outline"
              size="sm"
              disabled={sending || cooldown > 0}
              onClick={() => retry.mutate()}
            >
              {sending ? <Loader2 className="animate-spin" /> : notSent ? <Send /> : <RotateCw />}
              {sending
                ? "AI анализирует…"
                : cooldown > 0
                  ? `Повторно через ${cooldown} с`
                  : notSent
                    ? "Отправить в AI"
                    : "Отправить повторно"}
            </Button>
          </CardAction>
        )}
      </CardHeader>
      <CardContent className="grid gap-5">
        {ai && <InferenceView ai={ai} />}

        {waiting && (
          <div className="flex flex-col items-center gap-2 py-8 text-center text-sm text-muted-foreground">
            <Loader2 className="size-6 animate-spin text-primary" />
            AI анализирует заключение…
            <span className="text-xs">Решение можно принять, не дожидаясь ответа.</span>
          </div>
        )}

        {notSent && !sending && (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Заключение ещё не отправлено в AI.
            <br />
            <span className="text-xs">
              {study.can_act
                ? "Нажмите «Отправить в AI» или примите решение без рекомендации."
                : "Отправить может лечащий врач или главврач."}
            </span>
          </p>
        )}
        {notSent && sending && (
          <div className="flex flex-col items-center gap-2 py-8 text-center text-sm text-muted-foreground">
            <Loader2 className="size-6 animate-spin text-primary" />
            AI анализирует заключение…
          </div>
        )}

        {failed && (
          <Alert variant="destructive">
            <AlertTriangle />
            <AlertTitle>AI-сервис не отвечает</AlertTitle>
            <AlertDescription>
              {lastError && typeof lastError.payload.error === "string" && (
                <p>{lastError.payload.error}</p>
              )}
              <p>
                {!study.ai_auto
                  ? "Автоматическая отправка выключена — отправьте повторно вручную."
                  : study.ai_retry?.stopped
                    ? `Автоматические попытки остановлены после ${study.ai_retry.failures} ошибок — отправьте вручную.`
                    : study.ai_retry?.next_at
                      ? `Следующая автоматическая попытка — ${fmtDateTime(study.ai_retry.next_at)}.`
                      : "Запрос повторится автоматически."}{" "}
                Решение можно принять без рекомендации AI.
              </p>
            </AlertDescription>
          </Alert>
        )}

        {(failed || notSent) && retry.isError && (
          <p className="text-sm text-destructive">
            Повторная отправка не удалась: {errorMessage(retry.error)}
          </p>
        )}

        {decidedWithoutAI && (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Решение принято без рекомендации AI.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function Bar({ value, className }: { value: number; className?: string }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-background">
      <div
        className={cn("h-full rounded-full bg-primary transition-all", className)}
        style={{ width: `${Math.max(2, value * 100)}%` }}
      />
    </div>
  );
}

function InferenceView({ ai }: { ai: Inference }) {
  // Модель коллег не даёт ни уверенности, ни оценок вариантов, ни весов причин —
  // тогда показываем порядок (от главного к второстепенному), без процентов
  const weighted = ai.reasons.every((r) => r.weight != null);
  const maxWeight = Math.max(...ai.reasons.map((r) => r.weight ?? 0), 0.01);
  const label = useLabels();
  const proposed = [
    ...(ai.details.specialists ?? []).map((c) => label("specialists", c)),
    ...(ai.details.research_types ?? []).map((c) => label("research_types", c)),
  ];
  return (
    <div className="grid gap-5">
      <div
        className={cn(
          "rounded-lg p-4",
          ai.confidence != null ? confidenceTone(ai.confidence) : "bg-primary/10",
        )}
      >
        <div className="text-xs font-medium uppercase opacity-70">Рекомендация</div>
        <div className="mt-1 flex flex-wrap items-baseline justify-between gap-2">
          <span className="text-lg font-medium">{RECOMMENDATION_LABELS[ai.recommendation]}</span>
          {ai.confidence != null && (
            <span className="text-3xl font-medium tabular-nums">{pct(ai.confidence)}</span>
          )}
        </div>
        {proposed.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className="text-xs opacity-70">
              {ai.details.specialists?.length ? "Специалист:" : "Назначить:"}
            </span>
            {proposed.map((p) => (
              <span key={p} className="rounded-md bg-background/70 px-2 py-0.5 text-sm font-medium">
                {p}
              </span>
            ))}
          </div>
        )}
      </div>

      <section className="grid gap-2">
        <h3 className="text-sm font-medium">Варианты</h3>
        {ai.ranked_options.map((o, i) =>
          o.score == null ? (
            <div key={o.type} className="flex items-center gap-2 text-sm">
              <span
                className={cn(
                  "grid size-6 shrink-0 place-items-center rounded-full text-xs tabular-nums",
                  i === 0 ? "bg-primary text-primary-foreground" : "bg-background",
                )}
              >
                {i + 1}
              </span>
              <span className={cn(i === 0 && "font-medium")}>{RECOMMENDATION_LABELS[o.type]}</span>
            </div>
          ) : (
            <div key={o.type} className="grid gap-1">
              <div className="flex justify-between text-sm">
                <span className={cn(o.type === ai.recommendation && "font-medium")}>
                  {RECOMMENDATION_LABELS[o.type]}
                </span>
                <span className="tabular-nums text-muted-foreground">{pct(o.score)}</span>
              </div>
              <Bar
                value={o.score}
                className={o.type === ai.recommendation ? undefined : "bg-muted-foreground/40"}
              />
            </div>
          ),
        )}
      </section>

      <section className="grid gap-2">
        <h3 className="text-sm font-medium">Почему</h3>
        {weighted ? (
          <ul className="grid gap-2">
            {ai.reasons.map((r) => (
              <li
                key={r.code}
                className="grid grid-cols-[1fr_5rem_3rem] items-center gap-3 text-sm"
              >
                <span>{r.label}</span>
                <Bar value={(r.weight ?? 0) / maxWeight} className="bg-chart-3" />
                <span className="text-right tabular-nums text-muted-foreground">
                  {r.weight?.toFixed(2)}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <ol className="grid list-decimal gap-1.5 pl-5 text-sm marker:text-muted-foreground">
            {ai.reasons.map((r) => (
              <li key={r.code}>{r.label}</li>
            ))}
          </ol>
        )}
      </section>

      <div className="flex flex-wrap gap-x-4 gap-y-1 border-t pt-3 text-xs text-muted-foreground">
        <span>
          Модель:{" "}
          <span className="font-mono">
            {ai.model_name} {ai.model_version}
          </span>
        </span>
        <span>Источник: {SOURCE_LABELS[ai.source]}</span>
        <span>Время ответа: {ai.latency_ms} мс</span>
        <span>{fmtDateTime(ai.created_at)}</span>
      </div>
    </div>
  );
}
