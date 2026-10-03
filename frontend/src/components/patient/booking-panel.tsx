"use client";

import { CalendarCheck, Loader2, Star, Stethoscope } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api/client";
import { useBook, useDoctors, useSlots } from "@/lib/api/hooks";
import type { DoctorBrief } from "@/lib/api/types";
import { fmtDateTime, useLabels } from "@/lib/format";
import { cn } from "@/lib/utils";

import { SlotCalendar } from "./slot-calendar";

/**
 * Специальность (рекомендованная сверху) → врач → день и время → запись.
 * lockedDoctor — врач задан (повторный приём у лечащего врача): только день и время.
 */
export function BookingPanel({
  notificationId,
  suggested = [],
  suggestedSpecialties = [],
  lockedDoctor,
  onDone,
}: {
  notificationId?: string;
  suggested?: DoctorBrief[];
  suggestedSpecialties?: string[];
  lockedDoctor?: DoctorBrief;
  onDone?: () => void;
}) {
  const label = useLabels();
  const doctors = useDoctors();
  const book = useBook();
  // Рекомендованные: специальности из решения и специальности подходящих врачей (лечащего)
  const recommended = [
    ...new Set([...suggestedSpecialties, ...suggested.map((d) => d.specialty ?? "")]),
  ].filter(Boolean);
  const [specialty, setSpecialty] = useState<string | null>(recommended[0] ?? null);
  const [pickedDoctorId, setPickedDoctorId] = useState<string | null>(null);
  const [slot, setSlot] = useState<string | null>(null);

  const suggestedIds = new Set(suggested.map((d) => d.id));
  const allDoctors = doctors.data ?? suggested;

  // Только специальности, по которым есть врачи; рекомендованная — первой
  // Рекомендованные показываем, даже если таких врачей в клинике нет
  const specialties = [
    ...new Set([...recommended, ...allDoctors.map((d) => d.specialty)].filter(Boolean)),
  ]
    .map((code) => code as string)
    .sort(
      (a, b) =>
        Number(recommended.includes(b)) - Number(recommended.includes(a)) ||
        label("specialists", a).localeCompare(label("specialists", b), "ru"),
    );

  const inSpecialty = allDoctors
    .filter((d) => d.specialty === specialty)
    .sort((a, b) => Number(suggestedIds.has(b.id)) - Number(suggestedIds.has(a.id)));
  // Один врач в специальности — выбираем его сразу
  const doctorId =
    lockedDoctor?.id ?? pickedDoctorId ?? (inSpecialty.length === 1 ? inSpecialty[0].id : null);
  const doctor = lockedDoctor ?? inSpecialty.find((d) => d.id === doctorId);
  const slots = useSlots(doctorId, 14);

  function pickSpecialty(code: string) {
    setSpecialty(code);
    setPickedDoctorId(null);
    setSlot(null);
  }

  function pickDoctor(id: string) {
    setPickedDoctorId(id);
    setSlot(null);
  }

  function confirm() {
    if (!doctorId || !slot) return;
    book.mutate(
      {
        doctor_id: doctorId,
        scheduled_for: slot,
        notification_id: notificationId ?? null,
      },
      {
        onSuccess: (a) => {
          toast.success(`Вы записаны: ${a.doctor.full_name}, ${fmtDateTime(a.scheduled_for)}`);
          onDone?.();
        },
        onError: (err) => {
          toast.error(errorMessage(err));
          setSlot(null);
        },
      },
    );
  }

  return (
    <div className="grid gap-5">
      {lockedDoctor ? (
        <div className="flex items-center gap-2 rounded-xl bg-background p-3 text-sm">
          <Stethoscope className="size-4 text-primary" />
          <span>
            Повторный приём у лечащего врача:{" "}
            <span className="font-medium">{lockedDoctor.full_name}</span> (
            {label("specialists", lockedDoctor.specialty)})
          </span>
        </div>
      ) : (
        <>
          <section className="grid gap-2">
            <h3 className="text-sm font-medium">1. Специалист</h3>
            {doctors.isLoading && !suggested.length ? (
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
                    {recommended.includes(code) && <Star />}
                    {label("specialists", code)}
                  </Button>
                ))}
              </div>
            )}
            {recommended.length > 0 && (
              <p className="flex items-center gap-1 text-xs text-muted-foreground">
                <Star className="size-3" /> рекомендовано врачом
              </p>
            )}
          </section>

          {specialty && (
            <section className="grid gap-2">
              <h3 className="text-sm font-medium">2. Врач</h3>
              {!inSpecialty.length && !doctors.isLoading && (
                <p className="text-sm text-muted-foreground">
                  В клинике пока нет врача этой специальности. Выберите другого специалиста или
                  обратитесь к лечащему врачу.
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
                    {suggestedIds.has(d.id) && (
                      <Badge className="bg-amber-100 text-amber-800">
                        <Star /> Рекомендован
                      </Badge>
                    )}
                  </button>
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {doctorId && (
        <section className="grid gap-2">
          <h3 className="text-sm font-medium">
            {lockedDoctor ? "День и время" : "3. День и время"}
          </h3>
          {slots.isLoading ? (
            <Skeleton className="h-72" />
          ) : !slots.data?.length ? (
            <p className="text-sm text-muted-foreground">Нет свободного времени на 2 недели.</p>
          ) : (
            <SlotCalendar key={doctorId} days={slots.data} slot={slot} onSlotChange={setSlot} />
          )}
        </section>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
        <span className="text-sm text-muted-foreground">
          {doctor && slot
            ? `${doctor.full_name}, ${fmtDateTime(slot)}`
            : lockedDoctor
              ? "Выберите день и время"
              : "Выберите специалиста, врача и время"}
        </span>
        <Button onClick={confirm} disabled={!slot || book.isPending}>
          {book.isPending ? <Loader2 className="animate-spin" /> : <CalendarCheck />}
          Записаться
        </Button>
      </div>
    </div>
  );
}
