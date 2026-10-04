"use client";

import { AppShell } from "@/components/app-shell";
import { Skeleton } from "@/components/ui/skeleton";
import { WeekCalendar } from "@/components/week-calendar";
import { errorMessage } from "@/lib/api/client";
import { useAppointments } from "@/lib/api/hooks";
import { useAppointmentTarget, useRequirementText } from "@/lib/format";

export default function PatientCalendarPage() {
  return (
    <AppShell roles={["patient"]}>
      <CalendarView />
    </AppShell>
  );
}

function CalendarView() {
  const appointments = useAppointments();
  const target = useAppointmentTarget();
  const what = useRequirementText();

  return (
    <div className="grid gap-4">
      <div>
        <h1 className="text-3xl font-medium tracking-tight md:text-4xl">Мой календарь</h1>
        <p className="text-sm text-muted-foreground">Ваши записи к врачам и на исследования</p>
      </div>
      {appointments.isError && (
        <p className="text-sm text-destructive">{errorMessage(appointments.error)}</p>
      )}
      {appointments.isLoading ? (
        <Skeleton className="h-96 rounded-3xl" />
      ) : (
        <WeekCalendar
          appointments={appointments.data ?? []}
          summary={(n) => `На этой неделе записей: ${n}`}
          // Клик — карточка рекомендации, по которой запись
          cell={(a) => ({
            title: target(a),
            sub: what(a),
            href: a.notification_id ? `/patient#n-${a.notification_id}` : null,
          })}
        />
      )}
    </div>
  );
}
