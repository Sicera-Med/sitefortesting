"use client";

import { FilePlus2, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage } from "@/lib/api/client";
import { useCreateStudy, useDoctors, usePatients } from "@/lib/api/hooks";
import type { StudyType } from "@/lib/api/types";
import { useAuth } from "@/lib/auth";
import { useLabels } from "@/lib/format";

// Типы с шаблоном БФТ / справочником AI-команды (как STUDY_KINDS на backend)
const KINDS: { key: string; label: string; study_type: StudyType; body_region: string }[] = [
  { key: "ct_chest", label: "КТ органов грудной клетки", study_type: "ct", body_region: "chest" },
  {
    key: "xray_chest",
    label: "Рентгенография / ФЛГ ОГК",
    study_type: "xray",
    body_region: "chest",
  },
  { key: "mmg", label: "Маммография", study_type: "mammography", body_region: "breast" },
  { key: "ct_head", label: "КТ головного мозга", study_type: "ct", body_region: "head" },
];

const EXAMPLE = `Очаги и образования легких- не обнаружены
Плевральный выпот- не обнаружен
Грудная аорта- наибольшее значение диаметра восходящей части грудной аорты: 40 мм
Коронарный кальций- кальциевый индекс (Agatston): 164; CAC DRS A2`;

/** Предпросмотр: так же, как backend (domain/sr.py) делит строки «Поле- значение». */
function previewFields(text: string): { name: string; value: string }[] {
  const out: { name: string; value: string }[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim().replace(/^[•*·\-–—]\s+/, "");
    if (!line || /^описание:?$/i.test(line) || /^заключение/i.test(line)) continue;
    const dash = /\s*[-—–]\s+/.exec(line);
    const colon = line.indexOf(":");
    const cuts = [
      ...(dash ? [[dash.index, dash.index + dash[0].length]] : []),
      ...(colon > 0 ? [[colon, colon + 1]] : []),
    ].sort((a, b) => a[0] - b[0]);
    if (cuts.length && line.slice(0, cuts[0][0]).trim() && line.slice(cuts[0][1]).trim()) {
      out.push({ name: line.slice(0, cuts[0][0]).trim(), value: line.slice(cuts[0][1]).trim() });
    } else if (out.length) {
      out[out.length - 1].value += ` ${line}`;
    }
  }
  return out;
}

/** Новое исследование из сырых данных DICOM SR — дальше оно уходит в AI при открытии. */
export function NewStudyButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size="lg" onClick={() => setOpen(true)}>
        <FilePlus2 /> Новое исследование
      </Button>
      {open && <NewStudyDialog onClose={() => setOpen(false)} />}
    </>
  );
}

function NewStudyDialog({ onClose }: { onClose: () => void }) {
  const { user } = useAuth();
  const isChief = user?.role === "chief";
  const patients = usePatients();
  const doctors = useDoctors();
  const create = useCreateStudy();
  const router = useRouter();
  const label = useLabels();
  const [patientId, setPatientId] = useState("");
  const [kind, setKind] = useState(KINDS[0].key);
  const [doctorId, setDoctorId] = useState("");
  const [description, setDescription] = useState("");
  const [conclusion, setConclusion] = useState("");
  const fields = previewFields(description);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const k = KINDS.find((x) => x.key === kind)!;
    create.mutate(
      {
        patient_id: patientId,
        study_type: k.study_type,
        body_region: k.body_region,
        description,
        conclusion: conclusion.trim() || null,
        treating_doctor_id: isChief ? doctorId : null,
      },
      { onSuccess: (study) => router.push(`/studies/${study.id}`) },
    );
  }

  const select = "h-10 rounded-md border border-input bg-background px-2.5 text-[15px]";
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-3xl">
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Новое исследование</DialogTitle>
            <DialogDescription>
              Вставьте раздел «Описание» из DICOM SR — строки «Поле- значение», как на сайте
              «Третьего мнения». AI разберёт поля по шаблону БФТ.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label htmlFor="patient">Пациент</Label>
              <select
                id="patient"
                className={select}
                value={patientId}
                onChange={(e) => setPatientId(e.target.value)}
                required
              >
                <option value="" disabled>
                  Выберите…
                </option>
                {patients.data?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.full_name}, {p.age} лет
                  </option>
                ))}
              </select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="kind">Исследование</Label>
              <select
                id="kind"
                className={select}
                value={kind}
                onChange={(e) => setKind(e.target.value)}
              >
                {KINDS.map((k) => (
                  <option key={k.key} value={k.key}>
                    {k.label}
                  </option>
                ))}
              </select>
            </div>
            {isChief && (
              <div className="grid gap-1.5 sm:col-span-2">
                <Label htmlFor="doctor">Лечащий врач</Label>
                <select
                  id="doctor"
                  className={select}
                  value={doctorId}
                  onChange={(e) => setDoctorId(e.target.value)}
                  required
                >
                  <option value="" disabled>
                    Выберите…
                  </option>
                  {doctors.data?.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.full_name} — {label("specialists", d.specialty)}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label htmlFor="description">Описание (DICOM SR)</Label>
              <Textarea
                id="description"
                className="min-h-56 font-mono text-xs"
                placeholder={EXAMPLE}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
            <div className="grid content-start gap-1.5">
              <Label>Разобранные поля ({fields.length})</Label>
              <div className="max-h-56 min-h-56 overflow-y-auto rounded-md border bg-background p-2 text-xs">
                {fields.length ? (
                  <dl className="grid grid-cols-[minmax(6rem,10rem)_1fr] gap-x-3 gap-y-1">
                    {fields.map((f, i) => (
                      <div key={i} className="contents">
                        <dt className="text-muted-foreground">{f.name}</dt>
                        <dd>{f.value}</dd>
                      </div>
                    ))}
                  </dl>
                ) : (
                  <p className="text-muted-foreground">Здесь появятся поля протокола</p>
                )}
              </div>
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="conclusion">Заключение рентгенолога (необязательно)</Label>
            <Textarea
              id="conclusion"
              value={conclusion}
              onChange={(e) => setConclusion(e.target.value)}
            />
          </div>
          {create.isError && (
            <p className="text-sm text-destructive">{errorMessage(create.error)}</p>
          )}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              Отмена
            </Button>
            <Button
              type="submit"
              disabled={create.isPending || (!fields.length && !conclusion.trim())}
            >
              {create.isPending && <Loader2 className="animate-spin" />}
              Создать и отправить в AI
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
