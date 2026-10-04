"use client";

import { AlertTriangle, ExternalLink, FileText, Sparkles } from "lucide-react";

import type { SourceRef } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/**
 * Источник пункта рекомендации AI: документ (КР Минздрава, методичка НПКЦ ДиТ) со ссылкой
 * на официальную страницу. Нет документа — это предложение модели; ссылка модели, которую
 * документ не подтверждает, — с предупреждением.
 */
export function SourceLinks({
  refs,
  unconfirmed = [],
  compact = false,
  className,
}: {
  refs: SourceRef[];
  unconfirmed?: string[];
  compact?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("grid gap-1 text-xs", className)}>
      {refs.map((r) =>
        r.url ? (
          <a
            key={r.text}
            href={r.url}
            target="_blank"
            rel="noreferrer"
            title={r.text}
            className="inline-flex items-start gap-1 text-primary hover:underline"
          >
            <FileText className="mt-0.5 size-3.5 shrink-0" />
            <span className={cn(compact && "line-clamp-1")}>{r.text}</span>
            <ExternalLink className="mt-0.5 size-3 shrink-0" />
          </a>
        ) : (
          <span key={r.text} className="inline-flex items-start gap-1 text-muted-foreground">
            <FileText className="mt-0.5 size-3.5 shrink-0" />
            <span className={cn(compact && "line-clamp-1")}>{r.text}</span>
          </span>
        ),
      )}
      {!refs.length && !compact && (
        <span className="inline-flex items-center gap-1 text-muted-foreground">
          <Sparkles className="size-3.5" /> предложение модели, не из документа
        </span>
      )}
      {unconfirmed.length > 0 && !compact && (
        <span className="inline-flex items-center gap-1 text-amber-700">
          <AlertTriangle className="size-3.5" />
          модель сослалась на запись справочника без такого действия: {unconfirmed.join(", ")}
        </span>
      )}
    </div>
  );
}
