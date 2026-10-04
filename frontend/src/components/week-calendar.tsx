"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { Appointment } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const TZ = "Europe/Moscow"; // часовой пояс клиники (CLINIC_TZ)
const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

// Рабочее время — как в backend/app/domain/schedule.py: 9:00–17:00, приём 30 минут
const TIMES = Array.from({ length: 16 }, (_, i) => {
  const minutes = 9 * 60 + i * 30;
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
});

// Даты — строки YYYY-MM-DD в поясе клиники; арифметика — через UTC
function parse(date: string) {
  const [y, m, d] = date.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

function iso(d: Date) {
  return d.toISOString().slice(0, 10);
}

function addDays(date: string, n: number) {
  const d = parse(date);
  d.setUTCDate(d.getUTCDate() + n);
  return iso(d);
}

function clinicDate(ms: number) {
  return new Date(ms).toLocaleDateString("sv-SE", { timeZone: TZ }); // YYYY-MM-DD
}

function clinicTime(isoString: string) {
  return new Date(isoString).toLocaleTimeString("ru-RU", {
    timeZone: TZ,
    hour: "2-digit",
    minute: "2-digit",
  });
}

function mondayOf(date: string) {
  return addDays(date, -((parse(date).getUTCDay() + 6) % 7));
}

/** Рабочая неделя для «сегодня»: в субботу и воскресенье — следующая. */
function currentWeek(date: string) {
  const weekday = (parse(date).getUTCDay() + 6) % 7; // 0 — понедельник
  return weekday >= 5 ? addDays(mondayOf(date), 7) : mondayOf(date);
}

function dayLabel(date: string) {
  return parse(date).toLocaleDateString("ru-RU", {
    timeZone: "UTC",
    day: "numeric",
    month: "short",
  });
}

export type CellContent = { title: string; sub: string; href: string | null };

/**
 * Неделя пн–вс × приёмы 9:00–17:00 с записями. Общая для расписания врача и календаря
 * пациента: что писать в ячейке и куда ведёт клик — решает страница (cell).
 */
export function WeekCalendar({
  appointments,
  cell,
  summary,
}: {
  appointments: Appointment[];
  cell: (a: Appointment) => CellContent;
  summary?: (weekCount: number) => React.ReactNode;
}) {
  const [today] = useState(() => clinicDate(Date.now())); // относительно открытия страницы
  const [week, setWeek] = useState(() => currentWeek(clinicDate(Date.now())));
  const days = WEEKDAYS.map((_, i) => addDays(week, i));

  const byCell = new Map<string, Appointment>();
  let weekCount = 0;
  for (const a of appointments) {
    if (a.status !== "scheduled") continue;
    const date = clinicDate(new Date(a.scheduled_for).getTime());
    byCell.set(`${date} ${clinicTime(a.scheduled_for)}`, a);
    if (days.includes(date)) weekCount++;
  }

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm text-muted-foreground">{summary?.(weekCount)}</span>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" onClick={() => setWeek(addDays(week, -7))}>
            <ChevronLeft />
          </Button>
          <Button variant="outline" onClick={() => setWeek(currentWeek(today))}>
            Сегодня
          </Button>
          <Button variant="outline" size="icon" onClick={() => setWeek(addDays(week, 7))}>
            <ChevronRight />
          </Button>
          <span className="ml-2 text-sm text-muted-foreground tabular-nums">
            {dayLabel(days[0])} — {dayLabel(days[6])}
          </span>
        </div>
      </div>
      <div className="overflow-x-auto rounded-3xl bg-card p-4">
        <div className="grid min-w-[900px] grid-cols-[4rem_repeat(7,minmax(0,1fr))] gap-1 text-sm">
          <div />
          {days.map((d, i) => (
            <div
              key={d}
              className={cn(
                "rounded-xl px-2 py-1.5 text-center",
                i >= 5 && "text-muted-foreground",
                d === today && "bg-primary text-primary-foreground",
              )}
            >
              <span className="font-medium">{WEEKDAYS[i]}</span>{" "}
              <span className={cn(d !== today && "text-muted-foreground")}>{dayLabel(d)}</span>
            </div>
          ))}
          {TIMES.map((t) => (
            <Row key={t} time={t} days={days} today={today} byCell={byCell} cell={cell} />
          ))}
        </div>
      </div>
    </div>
  );
}

function Row({
  time,
  days,
  today,
  byCell,
  cell,
}: {
  time: string;
  days: string[];
  today: string;
  byCell: Map<string, Appointment>;
  cell: (a: Appointment) => CellContent;
}) {
  return (
    <>
      <div className="py-2 pr-2 text-right text-xs text-muted-foreground tabular-nums">{time}</div>
      {days.map((d, i) => {
        const a = byCell.get(`${d} ${time}`);
        if (!a)
          return (
            <div
              key={d}
              className={cn(
                "min-h-11 rounded-lg bg-background/60",
                // Выходные — приёма нет
                i >= 5 && "bg-muted/40",
                d === today && "bg-accent/40",
              )}
            />
          );
        const c = cell(a);
        const body = (
          <>
            <div className="truncate font-medium">{c.title}</div>
            <div className="truncate text-xs opacity-80">{c.sub}</div>
          </>
        );
        const cls =
          "block min-h-11 rounded-lg border-l-4 border-primary bg-primary/10 px-2 py-1 text-left";
        return c.href ? (
          <Link
            key={d}
            href={c.href}
            title={`${c.title} — ${c.sub}`}
            className={cn(cls, "transition-colors hover:bg-primary/20")}
          >
            {body}
          </Link>
        ) : (
          <div key={d} title={`${c.title} — ${c.sub}`} className={cls}>
            {body}
          </div>
        );
      })}
    </>
  );
}
