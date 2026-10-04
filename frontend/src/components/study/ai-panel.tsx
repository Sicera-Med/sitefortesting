"use client";

import { AlertTriangle, Bot, FileJson, Loader2 } from "lucide-react";
import { useState } from "react";

import { confidenceTone } from "@/components/study-badges";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage } from "@/lib/api/client";
import { useStudyAudit, useUploadAIResult } from "@/lib/api/hooks";
import type { Inference, StudyCard } from "@/lib/api/types";
import { fmtDateTime, pct, RECOMMENDATION_LABELS, useLabels } from "@/lib/format";
import { cn } from "@/lib/utils";

const SOURCE_LABELS = {
  mock: "тестовые данные",
  http: "AI-сервис",
  manual: "загружен вручную",
} as const;

/** Панель AI: анализ идёт сам; врач видит результат или честный статус «не отвечает». */
export function AIPanel({ study, canUpload }: { study: StudyCard; canUpload: boolean }) {
  const [uploadOpen, setUploadOpen] = useState(false);
  const audit = useStudyAudit(study.id);
  const ai = study.ai;
  const waiting = study.status === "new";
  const failed = study.status === "ai_failed";
  const decidedWithoutAI = !ai && !waiting && !failed;
  // Последняя ошибка AI — из аудита (что именно ответил или не ответил сервис)
  const lastError = [...(audit.data ?? [])].reverse().find((e) => e.action === "ai.failed");

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Bot className="size-5 text-primary" /> Рекомендация AI
        </CardTitle>
        {canUpload && !ai && (
          <CardAction>
            <Button
              variant="ghost"
              size="icon"
              title="Загрузить ответ AI вручную (JSON)"
              onClick={() => setUploadOpen(true)}
            >
              <FileJson />
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

        {failed && (
          <Alert variant="destructive">
            <AlertTriangle />
            <AlertTitle>AI-сервис не отвечает</AlertTitle>
            <AlertDescription>
              {lastError && typeof lastError.payload.error === "string" && (
                <p>{lastError.payload.error}</p>
              )}
              <p>Запрос повторяется автоматически. Решение можно принять без рекомендации AI.</p>
            </AlertDescription>
          </Alert>
        )}

        {decidedWithoutAI && (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Решение принято без рекомендации AI.
          </p>
        )}
      </CardContent>

      <UploadDialog studyId={study.id} open={uploadOpen} onOpenChange={setUploadOpen} />
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
  const maxWeight = Math.max(...ai.reasons.map((r) => r.weight), 0.01);
  const label = useLabels();
  const proposed = [
    ...(ai.details.specialists ?? []).map((c) => label("specialists", c)),
    ...(ai.details.research_types ?? []).map((c) => label("research_types", c)),
  ];
  return (
    <div className="grid gap-5">
      <div className={cn("rounded-lg p-4", confidenceTone(ai.confidence))}>
        <div className="text-xs font-medium uppercase opacity-70">Рекомендация</div>
        <div className="mt-1 flex flex-wrap items-baseline justify-between gap-2">
          <span className="text-lg font-medium">{RECOMMENDATION_LABELS[ai.recommendation]}</span>
          <span className="text-3xl font-medium tabular-nums">{pct(ai.confidence)}</span>
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
        {ai.ranked_options.map((o) => (
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
        ))}
      </section>

      <section className="grid gap-2">
        <h3 className="text-sm font-medium">Почему</h3>
        <ul className="grid gap-2">
          {ai.reasons.map((r) => (
            <li key={r.code} className="grid grid-cols-[1fr_5rem_3rem] items-center gap-3 text-sm">
              <span>{r.label}</span>
              <Bar value={r.weight / maxWeight} className="bg-chart-3" />
              <span className="text-right tabular-nums text-muted-foreground">
                {r.weight.toFixed(2)}
              </span>
            </li>
          ))}
        </ul>
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

const JSON_EXAMPLE = `{
  "model": { "name": "chest-ct-triage", "version": "0.3.1" },
  "recommendation": "additional_research",
  "confidence": 0.87,
  "ranked_options": [{ "type": "additional_research", "score": 0.87 }],
  "reasons": [{ "code": "nodule_8mm", "label": "Узел 8 мм S6", "weight": 0.42 }]
}`;

function UploadDialog({
  studyId,
  open,
  onOpenChange,
}: {
  studyId: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const upload = useUploadAIResult(studyId);
  const [text, setText] = useState("");
  const [parseError, setParseError] = useState<string | null>(null);

  function submit() {
    let payload: unknown;
    try {
      payload = JSON.parse(text);
    } catch {
      setParseError("Это не JSON");
      return;
    }
    setParseError(null);
    upload.mutate(payload, {
      onSuccess: () => {
        onOpenChange(false);
        setText("");
      },
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Загрузить ответ AI</DialogTitle>
          <DialogDescription>
            JSON в формате контракта §6.2 — пройдёт ту же валидацию, что и ответ сервиса.
          </DialogDescription>
        </DialogHeader>
        <Textarea
          className="min-h-56 font-mono text-xs"
          placeholder={JSON_EXAMPLE}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        {(parseError || upload.error) && (
          <p className="text-sm text-destructive">{parseError ?? errorMessage(upload.error)}</p>
        )}
        <DialogFooter>
          <Button onClick={submit} disabled={!text.trim() || upload.isPending}>
            {upload.isPending && <Loader2 className="animate-spin" />}
            Загрузить
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
