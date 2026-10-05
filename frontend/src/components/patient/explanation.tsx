"use client";

import { MessageCircleQuestion, Loader2 } from "lucide-react";
import { useEffect, useRef } from "react";

import { useExplain } from "@/lib/api/hooks";
import type { PatientNotification } from "@/lib/api/types";

/** «Что значит результат исследования» — B2C AI-команды; запрашивается один раз при открытии. */
export function Explanation({ item }: { item: PatientNotification }) {
  const explain = useExplain();
  const asked = useRef(false);
  const id = item.notification.id;
  const ready = item.explanation;
  const { mutate } = explain;
  useEffect(() => {
    if (!ready && !asked.current) {
      asked.current = true;
      mutate(id);
    }
  }, [ready, id, mutate]);

  return (
    <section className="grid gap-2 rounded-2xl border bg-card p-4">
      <h3 className="flex items-center gap-2 font-medium">
        <MessageCircleQuestion className="size-5 text-primary" /> Что значит результат исследования
      </h3>
      {ready ? (
        <>
          <p className="text-base leading-relaxed">{ready.summary}</p>
          {ready.terms.length > 0 && (
            <dl className="grid gap-1.5">
              {ready.terms.map((t) => (
                <div key={t.term}>
                  <dt className="inline font-medium">{t.term}</dt>
                  <dd className="inline text-muted-foreground"> — {t.explanation}</dd>
                </div>
              ))}
            </dl>
          )}
          <p className="text-xs text-muted-foreground">
            Объяснение подготовил AI-ассистент по протоколу исследования. Решение о лечении
            принимает врач.
          </p>
        </>
      ) : explain.isError ? (
        <p className="text-muted-foreground">
          Объяснение пока недоступно. Рекомендации врача — ниже.
        </p>
      ) : (
        <p className="inline-flex items-center gap-2 text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Готовим объяснение простым языком…
        </p>
      )}
    </section>
  );
}
