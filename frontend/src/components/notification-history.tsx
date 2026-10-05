"use client";

import { Ban, BellRing, Check, Clock, Mail, MessageSquare, X } from "lucide-react";

import type { Delivery, DeliveryStatus, Notification, NotificationChannel } from "@/lib/api/types";
import { fmtDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const CHANNEL_ICONS: Record<NotificationChannel, typeof Mail> = {
  sms: MessageSquare,
  email: Mail,
};

const STATUS: Record<DeliveryStatus, { label: string; icon: typeof Check; className: string }> = {
  sent: { label: "отправлено", icon: Check, className: "text-emerald-700" },
  pending: { label: "в очереди", icon: Clock, className: "text-amber-700" },
  failed: { label: "ошибка", icon: X, className: "text-red-700" },
  // Рассылка выключена (NOTIFY_REAL=false) или канал не настроен — причина в detail
  simulated: { label: "не отправлено", icon: Ban, className: "text-muted-foreground" },
};

/**
 * История отправок уведомления: первое уведомление и напоминания раз в неделю, пока пациент
 * не записался, — и когда будет следующее. Персоналу (`staff`) — статус каждой доставки.
 */
export function NotificationHistory({
  notification: n,
  staff = false,
}: {
  notification: Notification;
  staff?: boolean;
}) {
  const attempts = new Map<number, Delivery[]>();
  for (const d of n.deliveries) attempts.set(d.attempt, [...(attempts.get(d.attempt) ?? []), d]);

  return (
    <div className="grid gap-3 text-sm">
      <ol className="relative grid gap-3 border-l pl-5">
        {[...attempts.entries()].map(([attempt, items]) => (
          <li key={attempt} className="relative">
            <span className="absolute top-1.5 -left-[25px] size-2.5 rounded-full border-2 border-background bg-primary" />
            <div className="font-medium">
              {attempt === 0 ? "Уведомление" : `Напоминание ${attempt} из ${n.max_reminders}`}
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                {fmtDateTime(items[0].at)}
              </span>
            </div>
            {texts(items).map(([text, sms]) => (
              <p key={text} className="mt-1 text-muted-foreground">
                {sms && <span className="font-medium text-foreground">SMS: </span>}
                {text}
              </p>
            ))}
            <ul className="mt-1 flex flex-wrap gap-1.5">
              {items.map((d) => {
                const Icon = CHANNEL_ICONS[d.channel];
                const s = STATUS[d.status];
                return (
                  <li
                    key={`${d.channel}-${d.target}`}
                    title={d.detail ?? undefined}
                    className="inline-flex items-center gap-1 rounded-md bg-background px-2 py-0.5 text-xs"
                  >
                    <Icon className="size-3.5 text-muted-foreground" />
                    {d.target}
                    {staff && (
                      <span className={cn("inline-flex items-center gap-0.5", s.className)}>
                        · <s.icon className="size-3" />
                        {s.label}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
            {staff &&
              items
                .filter((d) => d.status === "failed" && d.detail)
                .map((d) => (
                  <p key={`err-${d.channel}-${d.target}`} className="mt-1 text-xs text-red-700">
                    {d.target}: {d.detail}
                  </p>
                ))}
          </li>
        ))}
      </ol>
      {n.next_reminder_at ? (
        <p className="inline-flex items-center gap-1.5 text-muted-foreground">
          <BellRing className="size-4" />
          Следующее напоминание — {fmtDateTime(n.next_reminder_at)} ({n.reminders_sent + 1} из{" "}
          {n.max_reminders})
        </p>
      ) : (
        n.reminders_sent >= n.max_reminders && (
          <p className="text-muted-foreground">
            Напоминания завершены: отправлено {n.reminders_sent} из {n.max_reminders}
          </p>
        )
      )}
    </div>
  );
}

/** Разные тексты попытки: [текст, это SMS] — SMS короче, чем email и соцсети. */
function texts(items: Delivery[]): [string, boolean][] {
  const seen = new Map<string, boolean>();
  for (const d of items) {
    if (d.text && !seen.has(d.text)) seen.set(d.text, d.channel === "sms");
  }
  return [...seen.entries()].sort((a, b) => Number(a[1]) - Number(b[1]));
}
