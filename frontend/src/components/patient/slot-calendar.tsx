"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { DaySlots } from "@/lib/api/types";
import { fmtTime } from "@/lib/format";
import { cn } from "@/lib/utils";

// Даты — строки YYYY-MM-DD в поясе клиники; считаем их через UTC, чтобы не зависеть от пояса браузера.
const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

function parse(date: string) {
  const [y, m, d] = date.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

function iso(d: Date) {
  return d.toISOString().slice(0, 10);
}

function monthKey(date: string) {
  return date.slice(0, 7); // YYYY-MM
}

function shiftMonth(key: string, delta: number) {
  const [y, m] = key.split("-").map(Number);
  return iso(new Date(Date.UTC(y, m - 1 + delta, 1))).slice(0, 7);
}

/** 6×7 клеток месяца, неделя с понедельника; null — дни соседних месяцев. */
function monthGrid(key: string): (string | null)[] {
  const first = parse(`${key}-01`);
  const offset = (first.getUTCDay() + 6) % 7;
  const daysInMonth = new Date(
    Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 0),
  ).getUTCDate();
  const cells: (string | null)[] = Array(offset).fill(null);
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push(`${key}-${String(d).padStart(2, "0")}`);
  }
  while (cells.length % 7) cells.push(null);
  return cells;
}

function monthTitle(key: string) {
  const s = parse(`${key}-01`).toLocaleDateString("ru-RU", {
    timeZone: "UTC",
    month: "long",
    year: "numeric",
  });
  return s.charAt(0).toUpperCase() + s.slice(1).replace(" г.", "");
}

function dayTitle(date: string) {
  return parse(date).toLocaleDateString("ru-RU", {
    timeZone: "UTC",
    weekday: "long",
    day: "numeric",
    month: "long",
  });
}

function todayInClinic() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Moscow" }).format(new Date());
}

/** Календарь месяца со свободными днями + время на выбранный день. */
export function SlotCalendar({
  days,
  slot,
  onSlotChange,
}: {
  days: DaySlots[];
  slot: string | null;
  onSlotChange: (slot: string | null) => void;
}) {
  const [today] = useState(todayInClinic);
  const byDate = new Map(days.map((d) => [d.date, d.slots]));
  const firstFree = days[0]?.date ?? today;

  const [selected, setSelected] = useState<string>(firstFree);
  const [month, setMonth] = useState(monthKey(firstFree));

  const minMonth = monthKey(today);
  const maxMonth = monthKey(days.at(-1)?.date ?? today);
  const selectedSlots = byDate.get(selected) ?? [];

  // Утро — до 13:00 по времени клиники
  const groups = [
    { title: "Утро", slots: selectedSlots.filter((s) => fmtTime(s) < "13:00") },
    {
      title: "День",
      slots: selectedSlots.filter((s) => fmtTime(s) >= "13:00"),
    },
  ];

  function pick(date: string) {
    setSelected(date);
    onSlotChange(null);
  }

  return (
    <div className="grid gap-4 md:grid-cols-[minmax(0,20rem)_1fr]">
      <div className="rounded-2xl bg-background p-3">
        <div className="mb-2 flex items-center justify-between">
          <Button
            variant="ghost"
            size="icon-sm"
            disabled={month <= minMonth}
            onClick={() => setMonth(shiftMonth(month, -1))}
            title="Предыдущий месяц"
          >
            <ChevronLeft />
          </Button>
          <span className="text-sm font-medium">{monthTitle(month)}</span>
          <Button
            variant="ghost"
            size="icon-sm"
            disabled={month >= maxMonth}
            onClick={() => setMonth(shiftMonth(month, 1))}
            title="Следующий месяц"
          >
            <ChevronRight />
          </Button>
        </div>

        <div className="grid grid-cols-7 gap-1 text-center">
          {WEEKDAYS.map((w, i) => (
            <div
              key={w}
              className={cn(
                "pb-1 text-xs font-medium text-muted-foreground",
                i >= 5 && "text-red-400",
              )}
            >
              {w}
            </div>
          ))}
          {monthGrid(month).map((date, i) => {
            if (!date) return <div key={`e${i}`} />;
            const free = byDate.get(date)?.length ?? 0;
            const isSelected = date === selected;
            return (
              <button
                key={date}
                type="button"
                disabled={!free}
                onClick={() => pick(date)}
                title={free ? `Свободно: ${free}` : "Нет приёма"}
                className={cn(
                  "relative flex aspect-square flex-col items-center justify-center rounded-lg text-sm tabular-nums transition-colors",
                  free
                    ? "font-medium hover:bg-primary/10"
                    : "cursor-default text-muted-foreground/40",
                  date === today && !isSelected && "ring-1 ring-primary/50",
                  isSelected && "bg-primary text-primary-foreground hover:bg-primary",
                )}
              >
                {Number(date.slice(8))}
                {free > 0 && (
                  <span
                    className={cn(
                      "absolute bottom-1 size-1 rounded-full",
                      isSelected ? "bg-primary-foreground" : "bg-emerald-500",
                    )}
                  />
                )}
              </button>
            );
          })}
        </div>
        <div className="mt-3 flex items-center gap-3 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <span className="size-1.5 rounded-full bg-emerald-500" /> есть время
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="size-3 rounded ring-1 ring-primary/50" /> сегодня
          </span>
        </div>
      </div>

      <div className="grid content-start gap-3">
        <div className="text-sm font-medium first-letter:uppercase">{dayTitle(selected)}</div>
        {!selectedSlots.length ? (
          <p className="text-sm text-muted-foreground">В этот день нет свободного времени.</p>
        ) : (
          groups.map((g) =>
            g.slots.length ? (
              <div key={g.title} className="grid gap-1.5">
                <div className="text-xs text-muted-foreground">{g.title}</div>
                <div className="grid grid-cols-4 gap-1.5 sm:grid-cols-5">
                  {g.slots.map((s) => (
                    <Button
                      key={s}
                      size="sm"
                      variant={s === slot ? "default" : "outline"}
                      className="tabular-nums"
                      onClick={() => onSlotChange(s)}
                    >
                      {fmtTime(s)}
                    </Button>
                  ))}
                </div>
              </div>
            ) : null,
          )
        )}
      </div>
    </div>
  );
}
