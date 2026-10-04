"use client";

import { CalendarDays, Loader2, Pencil, UserPlus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { errorMessage } from "@/lib/api/client";
import {
  useCreateDoctor,
  useDictionaries,
  useStaffDoctors,
  useUpdateDoctor,
} from "@/lib/api/hooks";
import type { StaffDoctor } from "@/lib/api/types";
import { useLabels } from "@/lib/format";
import { cn } from "@/lib/utils";

export default function DoctorsPage() {
  return (
    <AppShell roles={["chief"]}>
      <DoctorsView />
    </AppShell>
  );
}

function DoctorsView() {
  const { data, isLoading, error } = useStaffDoctors();
  const update = useUpdateDoctor();
  const label = useLabels();
  // undefined — диалог закрыт, null — новый врач
  const [editing, setEditing] = useState<StaffDoctor | null | undefined>(undefined);
  const active = data?.filter((d) => d.active).length ?? 0;

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-medium tracking-tight md:text-4xl">Врачи</h1>
          <p className="text-sm text-muted-foreground">
            {data ? `${active} с доступом из ${data.length}` : " "}
          </p>
        </div>
        <Button onClick={() => setEditing(null)}>
          <UserPlus /> Добавить врача
        </Button>
      </div>

      {update.isError && <p className="text-sm text-destructive">{errorMessage(update.error)}</p>}
      <div className="overflow-hidden rounded-3xl bg-card px-3 py-2">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Врач</TableHead>
              <TableHead>Специальность</TableHead>
              <TableHead className="text-right">Ждут решения</TableHead>
              <TableHead className="text-right">Решений</TableHead>
              <TableHead className="text-right">Приёмов за 7 дней</TableHead>
              <TableHead>Доступ</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading &&
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  <TableCell colSpan={7}>
                    <Skeleton className="h-6 w-full" />
                  </TableCell>
                </TableRow>
              ))}
            {error && (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-destructive">
                  {errorMessage(error)}
                </TableCell>
              </TableRow>
            )}
            {data?.map((d) => (
              <TableRow key={d.id} className={cn(!d.active && "text-muted-foreground")}>
                <TableCell>
                  <div className="font-medium">{d.full_name}</div>
                  <div className="text-xs text-muted-foreground">{d.email}</div>
                </TableCell>
                <TableCell>{label("specialists", d.specialty)}</TableCell>
                <TableCell className="text-right tabular-nums">
                  <span className={cn(d.open_studies > 0 && d.active && "font-medium")}>
                    {d.open_studies}
                  </span>
                </TableCell>
                <TableCell className="text-right tabular-nums">{d.decisions}</TableCell>
                <TableCell className="text-right tabular-nums">{d.upcoming_appointments}</TableCell>
                <TableCell>
                  <label className="inline-flex cursor-pointer items-center gap-2">
                    <input
                      type="checkbox"
                      className="size-4 accent-primary"
                      checked={d.active}
                      disabled={update.isPending}
                      onChange={() => update.mutate({ id: d.id, active: !d.active })}
                    />
                    {d.active ? <span>есть</span> : <Badge variant="secondary">отключён</Badge>}
                  </label>
                </TableCell>
                <TableCell>
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      title="Расписание"
                      render={<Link href={`/schedule?doctor=${d.id}`} />}
                      nativeButton={false}
                    >
                      <CalendarDays />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      title="Изменить"
                      onClick={() => setEditing(d)}
                    >
                      <Pencil />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <p className="text-sm text-muted-foreground">
        У отключённого врача нельзя войти и записаться к нему. Его пациентов без решения передайте
        другому врачу в карточке исследования.
      </p>

      {editing !== undefined && (
        <DoctorDialog
          key={editing?.id ?? "new"}
          doctor={editing}
          onClose={() => setEditing(undefined)}
        />
      )}
    </div>
  );
}

function DoctorDialog({ doctor, onClose }: { doctor: StaffDoctor | null; onClose: () => void }) {
  const dicts = useDictionaries();
  const create = useCreateDoctor();
  const update = useUpdateDoctor();
  const [fullName, setFullName] = useState(doctor?.full_name ?? "");
  const [email, setEmail] = useState("");
  const [specialty, setSpecialty] = useState(doctor?.specialty ?? "");
  const [password, setPassword] = useState("");
  const mutation = doctor ? update : create;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (doctor) {
      update.mutate({ id: doctor.id, full_name: fullName, specialty }, { onSuccess: onClose });
    } else {
      create.mutate({ full_name: fullName, email, specialty, password }, { onSuccess: onClose });
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{doctor ? "Изменить врача" : "Новый врач"}</DialogTitle>
            <DialogDescription>
              {doctor ? doctor.email : "Врач сможет войти по email и паролю"}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-1.5">
            <Label htmlFor="full_name">ФИО</Label>
            <Input
              id="full_name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
            />
          </div>
          {!doctor && (
            <div className="grid gap-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
          )}
          <div className="grid gap-1.5">
            <Label htmlFor="specialty">Специальность</Label>
            <select
              id="specialty"
              className="h-9 rounded-md border border-input bg-transparent px-2.5 text-sm"
              value={specialty}
              onChange={(e) => setSpecialty(e.target.value)}
              required
            >
              <option value="" disabled>
                Выберите…
              </option>
              {dicts.data?.specialists.map((s) => (
                <option key={s.code} value={s.code}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          {!doctor && (
            <div className="grid gap-1.5">
              <Label htmlFor="password">Пароль</Label>
              <Input
                id="password"
                type="text"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={4}
                required
              />
            </div>
          )}
          {mutation.isError && (
            <p className="text-sm text-destructive">{errorMessage(mutation.error)}</p>
          )}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              Отмена
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending && <Loader2 className="animate-spin" />}
              {doctor ? "Сохранить" : "Добавить"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
