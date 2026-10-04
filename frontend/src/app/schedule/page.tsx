"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api/client";
import { useAppointments, useDoctors } from "@/lib/api/hooks";
import type { Appointment } from "@/lib/api/types";
import { useAuth } from "@/lib/auth";
import { useLabels, useRequirementLabel } from "@/lib/format";
import { cn } from "@/lib/utils";

const TZ = "Europe/Moscow"; // часовой пояс клиники (CLINIC_TZ)
const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт"];

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

export default function SchedulePage() {
  return (
    <AppShell roles={["doctor", "chief"]}>
      {/* useSearchParams требует Suspense при статической сборке */}
      <Suspense fallback={<Skeleton className="h-96 rounded-3xl" />}>
        <ScheduleView />
      </Suspense>
    </AppShell>
  );
}

function ScheduleView() {
  const { user } = useAuth();
  const isChief = user?.role === "chief";
  const params = useSearchParams();
  const router = useRouter();
  const doctors = useDoctors();
  // Врач видит своё расписание; главврач выбирает врача (?doctor=…)
  const doctorId = isChief ? (params.get("doctor") ?? doctors.data?.[0]?.id ?? null) : null;
  const doctor = isChief ? doctors.data?.find((d) => d.id === doctorId) : user;
  const appointments = useAppointments(isChief ? doctorId : null);
  const label = useLabels();

  const [today] = useState(() => clinicDate(Date.now())); // относительно открытия страницы
  const [week, setWeek] = useState(() => currentWeek(clinicDate(Date.now())));
  const days = WEEKDAYS.map((_, i) => addDays(week, i));

  const byCell = new Map<string, Appointment>();
  let weekCount = 0;
  for (const a of appointments.data ?? []) {
    if (a.status !== "scheduled") continue;
    const date = clinicDate(new Date(a.scheduled_for).getTime());
    byCell.set(`${date} ${clinicTime(a.scheduled_for)}`, a);
    if (days.includes(date)) weekCount++;
  }

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-medium tracking-tight md:text-4xl">Расписание</h1>
          <p className="text-sm text-muted-foreground">
            {doctor
              ? `${doctor.full_name}${doctor.specialty ? `, ${label("specialists", doctor.specialty).toLowerCase()}` : ""}`
              : " "}
            {appointments.data && ` · на этой неделе приёмов: ${weekCount}`}
          </p>
        </div>
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
            {dayLabel(days[0])} — {dayLabel(days[4])}
          </span>
        </div>
      </div>

      {isChief && (
        <div className="flex flex-wrap gap-1.5">
          {doctors.data?.map((d) => (
            <Button
              key={d.id}
              size="sm"
              variant={d.id === doctorId ? "default" : "outline"}
              onClick={() => router.replace(`/schedule?doctor=${d.id}`)}
            >
              {d.full_name.split(" ")[0]} · {label("specialists", d.specialty)}
            </Button>
          ))}
        </div>
      )}

      {appointments.isError && (
        <p className="text-sm text-destructive">{errorMessage(appointments.error)}</p>
      )}
      {appointments.isLoading ? (
        <Skeleton className="h-96 rounded-3xl" />
      ) : (
        <div className="overflow-x-auto rounded-3xl bg-card p-4">
          <div className="grid min-w-[720px] grid-cols-[4rem_repeat(5,minmax(0,1fr))] gap-1 text-sm">
            <div />
            {days.map((d, i) => (
              <div
                key={d}
                className={cn(
                  "rounded-xl px-2 py-1.5 text-center",
                  d === today && "bg-primary text-primary-foreground",
                )}
              >
                <span className="font-medium">{WEEKDAYS[i]}</span>{" "}
                <span className={cn(d !== today && "text-muted-foreground")}>{dayLabel(d)}</span>
              </div>
            ))}
            {TIMES.map((t) => (
              <Row key={t} time={t} days={days} today={today} byCell={byCell} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Row({
  time,
  days,
  today,
  byCell,
}: {
  time: string;
  days: string[];
  today: string;
  byCell: Map<string, Appointment>;
}) {
  const requirementLabel = useRequirementLabel();
  return (
    <>
      <div className="py-2 pr-2 text-right text-xs text-muted-foreground tabular-nums">{time}</div>
      {days.map((d) => {
        const a = byCell.get(`${d} ${time}`);
        if (!a)
          return (
            <div
              key={d}
              className={cn("min-h-11 rounded-lg bg-background/60", d === today && "bg-accent/40")}
            />
          );
        const what = a.requirement
          ? requirementLabel({
              kind: a.requirement.split(":")[0] as "treating" | "specialist" | "research",
              code: a.requirement.split(":")[1] ?? null,
            })
          : "Запись без направления";
        const body = (
          <>
            <div className="truncate font-medium">{a.patient.full_name}</div>
            <div className="truncate text-xs opacity-80">{what}</div>
          </>
        );
        const cls =
          "block min-h-11 rounded-lg border-l-4 border-primary bg-primary/10 px-2 py-1 text-left";
        return a.study_id ? (
          <Link
            key={d}
            href={`/studies/${a.study_id}`}
            title={`${a.patient.full_name}, тел. ${a.patient.phone}`}
            className={cn(cls, "transition-colors hover:bg-primary/20")}
          >
            {body}
          </Link>
        ) : (
          <div key={d} title={`${a.patient.full_name}, тел. ${a.patient.phone}`} className={cls}>
            {body}
          </div>
        );
      })}
    </>
  );
}
