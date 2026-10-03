"use client";

// Простые графики дашборда на HTML/CSS: стат-плитки, полосы-индикаторы, тепловая матрица.
// Цвет: одна серия — акцент (--primary), трек — светлый шаг того же оттенка (--accent);
// величина в матрице — последовательная шкала одного оттенка. Текст — только текстовыми токенами.

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Rate } from "@/lib/api/types";
import { pct } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Подсказка при наведении/фокусе; значение всегда продублировано на странице. */
export function Tip({
  content,
  className,
  style,
  children,
}: {
  content: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  children: React.ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={<div tabIndex={0} className={cn("outline-none", className)} style={style} />}
      >
        {children}
      </TooltipTrigger>
      <TooltipContent>{content}</TooltipContent>
    </Tooltip>
  );
}

export function StatTile({
  label,
  value,
  note,
  hero,
  className,
}: {
  label: string;
  value: string;
  note?: React.ReactNode;
  hero?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col justify-between gap-3 rounded-3xl bg-card p-6", className)}>
      <div className="text-sm text-muted-foreground">{label}</div>
      <div>
        <div
          className={cn(
            "leading-none font-medium tracking-tight",
            hero ? "text-6xl md:text-7xl" : "text-4xl",
          )}
        >
          {value}
        </div>
        {note && <div className="mt-2 text-sm text-muted-foreground">{note}</div>}
      </div>
    </div>
  );
}

/** Полоса-индикатор доли: заливка — акцент, трек — светлый шаг того же оттенка. */
export function Meter({ value, className }: { value: number | null; className?: string }) {
  return (
    <div className={cn("h-3 w-full overflow-hidden rounded-full bg-accent", className)}>
      {value != null && value > 0 && (
        <div
          className="h-full rounded-full bg-primary transition-[width]"
          style={{ width: `${Math.max(value * 100, 2)}%` }}
        />
      )}
    </div>
  );
}

/** Строка «подпись — значение — индикатор» с подсказкой «N из M». */
export function RateRow({
  label,
  sub,
  rate,
  unit = "решений",
}: {
  label: React.ReactNode;
  sub?: React.ReactNode;
  rate: Rate;
  unit?: string;
}) {
  return (
    <Tip
      className="grid gap-2 rounded-xl focus-visible:ring-3 focus-visible:ring-ring/50"
      content={
        rate.total ? `${rate.agreed} из ${rate.total} ${unit} · ${pct(rate.rate, 1)}` : "Нет данных"
      }
    >
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <div className="font-medium">{label}</div>
          {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
        </div>
        <div className="text-right">
          <span className="text-2xl font-medium">{pct(rate.rate)}</span>
          <span className="ml-2 text-xs text-muted-foreground tabular-nums">
            {rate.agreed}/{rate.total}
          </span>
        </div>
      </div>
      <Meter value={rate.rate} />
    </Tip>
  );
}

/**
 * Матрица «AI рекомендовал (строки) → врач выбрал (столбцы)».
 * Диагональ — согласие. Насыщенность ячейки — число решений (один оттенок).
 */
export function ConfusionMatrix({
  labels,
  matrix,
  labelOf,
}: {
  labels: string[];
  matrix: number[][];
  labelOf: (code: string) => string;
}) {
  const max = Math.max(1, ...matrix.flat());
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-1 text-sm">
        <thead>
          <tr>
            <th className="w-40 p-2 text-left align-bottom text-xs font-normal text-muted-foreground">
              AI ↓ · врач →
            </th>
            {labels.map((l) => (
              <th
                key={l}
                scope="col"
                className="p-2 text-left align-bottom text-xs font-normal text-muted-foreground"
              >
                {labelOf(l)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {labels.map((ai, i) => (
            <tr key={ai}>
              <th scope="row" className="p-2 text-left text-xs font-normal text-muted-foreground">
                {labelOf(ai)}
              </th>
              {labels.map((doc, j) => {
                const n = matrix[i][j];
                const share = n / max;
                const strong = share >= 0.8; // белый текст — только на насыщенной заливке
                const diagonal = i === j;
                return (
                  <td key={doc} className="p-0">
                    <Tip
                      className={cn(
                        "flex h-16 items-center justify-center rounded-xl text-lg font-medium tabular-nums transition-[filter] hover:brightness-95 focus-visible:ring-3 focus-visible:ring-ring/50",
                        strong ? "text-primary-foreground" : "text-foreground",
                        n === 0 && "text-muted-foreground",
                        diagonal && "ring-2 ring-primary/30 ring-inset",
                      )}
                      style={{
                        background:
                          n === 0
                            ? "var(--background)"
                            : `color-mix(in oklab, var(--primary) ${Math.round(15 + share * 85)}%, var(--background))`,
                      }}
                      content={`AI: ${labelOf(ai)} → врач: ${labelOf(doc)} — ${n} ${
                        diagonal ? "(согласие)" : "(расхождение)"
                      }`}
                    >
                      {n}
                    </Tip>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
