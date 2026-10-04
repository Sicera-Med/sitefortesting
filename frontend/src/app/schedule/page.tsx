"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { WeekCalendar } from "@/components/week-calendar";
import { errorMessage } from "@/lib/api/client";
import { useAppointments, useDoctors } from "@/lib/api/hooks";
import { useAuth } from "@/lib/auth";
import { useLabels, useRequirementText } from "@/lib/format";

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
  const what = useRequirementText();

  return (
    <div className="grid gap-4">
      <div>
        <h1 className="text-3xl font-medium tracking-tight md:text-4xl">Расписание</h1>
        <p className="text-sm text-muted-foreground">
          {doctor
            ? `${doctor.full_name}${doctor.specialty ? `, ${label("specialists", doctor.specialty).toLowerCase()}` : ""}`
            : " "}
        </p>
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
        <WeekCalendar
          appointments={appointments.data ?? []}
          summary={(n) => `На этой неделе приёмов: ${n}`}
          // Клик — все исследования этого пациента (список с поиском по ФИО)
          cell={(a) => ({
            title: a.patient.full_name,
            sub: what(a),
            href: `/studies?patient=${encodeURIComponent(a.patient.full_name)}`,
          })}
        />
      )}
    </div>
  );
}
