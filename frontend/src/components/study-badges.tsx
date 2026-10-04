// Бейджи статуса Study, рекомендации AI с уверенностью и согласия врача с AI.

import { Check, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { RecommendationType, StudyStatus } from "@/lib/api/types";
import { pct, RECOMMENDATION_LABELS, STATUS_LABELS } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATUS_STYLE: Record<StudyStatus, string> = {
  new: "bg-sky-100 text-sky-800",
  ai_ready: "bg-violet-100 text-violet-800",
  ai_failed: "bg-red-100 text-red-800",
  decided: "bg-amber-100 text-amber-800",
  notified: "bg-teal-100 text-teal-800",
  completed: "bg-emerald-100 text-emerald-800",
};

export function StatusBadge({ status }: { status: StudyStatus }) {
  return <Badge className={STATUS_STYLE[status]}>{STATUS_LABELS[status]}</Badge>;
}

const HIGH_CONFIDENCE = 0.7; // AI_HIGH_CONFIDENCE на backend

export function confidenceTone(c: number) {
  if (c >= 0.85) return "bg-emerald-100 text-emerald-800";
  if (c >= HIGH_CONFIDENCE) return "bg-lime-100 text-lime-800";
  if (c >= 0.5) return "bg-amber-100 text-amber-800";
  return "bg-red-100 text-red-800";
}

export function ConfidenceBadge({ value, className }: { value: number; className?: string }) {
  return (
    <Badge className={cn("tabular-nums", confidenceTone(value), className)}>{pct(value)}</Badge>
  );
}

export function AIBadge({
  recommendation,
  confidence,
}: {
  recommendation: RecommendationType;
  confidence: number | null;
}) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="text-sm">{RECOMMENDATION_LABELS[recommendation]}</span>
      {confidence != null && <ConfidenceBadge value={confidence} />}
    </span>
  );
}

export function AgreementBadge({ accepted }: { accepted: boolean | null }) {
  if (accepted == null) return <Badge variant="outline">Без AI</Badge>;
  return accepted ? (
    <Badge className="bg-emerald-100 text-emerald-800">
      <Check /> Согласен с AI
    </Badge>
  ) : (
    <Badge className="bg-red-100 text-red-800">
      <X /> Не согласен с AI
    </Badge>
  );
}
