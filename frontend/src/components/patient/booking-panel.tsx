"use client";

import { CalendarCheck, FlaskConical, Loader2, Stethoscope } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api/client";
import { useBook, useDoctors, useResearchSlots, useSlots } from "@/lib/api/hooks";
import type { DoctorBrief } from "@/lib/api/types";
import { fmtDateTime, useLabels } from "@/lib/format";
import { cn } from "@/lib/utils";

import { SlotCalendar } from "./slot-calendar";

/** Куда записываемся: по направлению из решения врача или свободно. */
export type BookingTarget =
  | { kind: "free" }
  | { kind: "treating"; doctor: DoctorBrief }
  | { kind: "specialist"; code: string }
  | { kind: "research"; code: string };

/**
 * Запись: врач → день и время, или сразу день и время.
 * - treating — повторный приём у лечащего врача: только день и время;
 * - specialist — специальность задана направлением: выбор врача → день и время;
 * - research — кабинет исследования: только день и время;
 * - free — специальность → врач → день и время.
 */
export function BookingPanel({
  target = { kind: "free" },
  notificationId,
  requirement,
  onDone,
}: {
  target?: BookingTarget;
  notificationId?: string;
  requirement?: string;
  onDone?: () => void;
}) {
  const label = useLabels();
  const doctors = useDoctors();
  const book = useBook();
  const [freeSpecialty, setFreeSpecialty] = useState<string | null>(null);
  const [pickedDoctorId, setPickedDoctorId] = useState<string | null>(null);
  const [slot, setSlot] = useState<string | null>(null);

  const research = target.kind === "research" ? target.code : null;
  const specialty = target.kind === "specialist" ? target.code : freeSpecialty;
  const allDoctors = doctors.data ?? [];
  const specialties = [...new Set(allDoctors.map((d) => d.specialty).filter(Boolean))]
    .map((code) => code as string)
    .sort((a, b) => label("specialists", a).localeCompare(label("specialists", b), "ru"));
  const inSpecialty = allDoctors.filter((d) => d.specialty === specialty);

  // Один врач в специальности — выбираем его сразу
  const doctorId =
    target.kind === "treating"
      ? target.doctor.id
      : target.kind === "research"
        ? null
        : (pickedDoctorId ?? (inSpecialty.length === 1 ? inSpecialty[0].id : null));
  const doctor =
    target.kind === "treating" ? target.doctor : inSpecialty.find((d) => d.id === doctorId);
  const doctorSlots = useSlots(doctorId, 14);
  const researchSlots = useResearchSlots(research, 14);
  const slots = research ? researchSlots : doctorSlots;
  const resource = research ?? doctorId;

  function pickSpecialty(code: string) {
    setFreeSpecialty(code);
    setPickedDoctorId(null);
    setSlot(null);
  }

  function pickDoctor(id: string) {
    setPickedDoctorId(id);
    setSlot(null);
  }

  function confirm() {
    if (!resource || !slot) return;
    book.mutate(
      {
        doctor_id: doctorId,
        research_type: research,
        scheduled_for: slot,
        notification_id: notificationId ?? null,
        requirement: requirement ?? null,
      },
      {
        onSuccess: () => onDone?.(),
        // Слот могли занять — сбрасываем выбор, ошибка видна над кнопкой
        onError: () => setSlot(null),
      },
    );
  }

  const step = (n: number) => (target.kind === "free" ? `${n}. ` : "");

  return (
    <div className="grid gap-5">
      {target.kind === "treating" && (
        <Fixed icon={<Stethoscope className="size-4 text-primary" />}>
          Повторный приём у лечащего врача:{" "}
          <span className="font-medium">{target.doctor.full_name}</span> (
          {label("specialists", target.doctor.specialty)})
        </Fixed>
      )}
      {target.kind === "research" && (
        <Fixed icon={<FlaskConical className="size-4 text-primary" />}>
          Исследование: <span className="font-medium">{label("research_types", target.code)}</span>
        </Fixed>
      )}

      {target.kind === "free" && (
        <section className="grid gap-2">
          <h3 className="text-sm font-medium">1. Специалист</h3>
          {doctors.isLoading ? (
            <Skeleton className="h-10" />
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {specialties.map((code) => (
                <Button
                  key={code}
                  size="sm"
                  variant={code === specialty ? "default" : "outline"}
                  onClick={() => pickSpecialty(code)}
                >
                  {label("specialists", code)}
                </Button>
              ))}
            </div>
          )}
        </section>
      )}

      {(target.kind === "free" || target.kind === "specialist") && specialty && (
        <section className="grid gap-2">
          <h3 className="text-sm font-medium">
            {step(2)}
            {target.kind === "specialist" ? `${label("specialists", specialty)}: врач` : "Врач"}
          </h3>
          {!inSpecialty.length && !doctors.isLoading && (
            <p className="text-sm text-muted-foreground">
              В клинике пока нет врача этой специальности. Обратитесь к лечащему врачу.
            </p>
          )}
          <div className="grid gap-2 sm:grid-cols-2">
            {inSpecialty.map((d) => (
              <button
                key={d.id}
                type="button"
                onClick={() => pickDoctor(d.id)}
                className={cn(
                  "flex items-center justify-between gap-2 rounded-xl border bg-background p-3 text-left text-sm transition-colors hover:border-primary/40",
                  d.id === doctorId && "border-primary bg-primary/5 hover:bg-primary/5",
                )}
              >
                <span className="grid">
                  <span className="font-medium">{d.full_name}</span>
                  <span className="text-xs text-muted-foreground">
                    {label("specialists", d.specialty)}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </section>
      )}

      {resource && (
        <section className="grid gap-2">
          <h3 className="text-sm font-medium">{step(3)}День и время</h3>
          {slots.isLoading ? (
            <Skeleton className="h-72" />
          ) : !slots.data?.length ? (
            <p className="text-sm text-muted-foreground">Нет свободного времени на 2 недели.</p>
          ) : (
            <SlotCalendar
              key={resource}
              days={slots.data}
              slot={slot}
              onSlotChange={(s) => {
                book.reset();
                setSlot(s);
              }}
            />
          )}
        </section>
      )}

      {book.isError && <p className="text-sm text-destructive">{errorMessage(book.error)}</p>}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
        <span className="text-sm text-muted-foreground">
          {slot
            ? `${research ? label("research_types", research) : doctor?.full_name}, ${fmtDateTime(slot)}`
            : resource
              ? "Выберите день и время"
              : target.kind === "free"
                ? "Выберите специалиста, врача и время"
                : "Выберите врача и время"}
        </span>
        <Button onClick={confirm} disabled={!slot || book.isPending}>
          {book.isPending ? <Loader2 className="animate-spin" /> : <CalendarCheck />}
          Записаться
        </Button>
      </div>
    </div>
  );
}

function Fixed({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 rounded-xl bg-background p-3 text-sm">
      {icon}
      <span>{children}</span>
    </div>
  );
}
