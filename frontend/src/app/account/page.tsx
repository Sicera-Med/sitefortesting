"use client";

import { Bell, Check, KeyRound, Loader2, UserRound } from "lucide-react";
import { useState } from "react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api/client";
import { useAccount, useChangePassword, useUpdateAccount } from "@/lib/api/hooks";
import type { Account, NotificationChannel } from "@/lib/api/types";
import { CHANNEL_LABELS, fmtDate, ROLE_LABELS, useLabels } from "@/lib/format";
import { cn } from "@/lib/utils";

const CHANNELS: NotificationChannel[] = ["sms", "email"];
// Какой контакт нужен для канала
const CHANNEL_CONTACT: Record<NotificationChannel, string> = {
  sms: "нужен телефон",
  email: "нужен email",
};

export default function AccountPage() {
  return (
    <AppShell roles={["doctor", "chief", "manager", "patient"]}>
      <AccountView />
    </AppShell>
  );
}

function AccountView() {
  const { data, isLoading, error } = useAccount();
  if (isLoading) return <Skeleton className="mx-auto h-96 max-w-3xl rounded-3xl" />;
  if (error || !data) return <p className="text-sm text-destructive">{errorMessage(error)}</p>;

  const isPatient = data.role === "patient";
  return (
    <div className="mx-auto grid max-w-3xl gap-6">
      <div>
        <h1 className="text-3xl font-medium tracking-tight md:text-4xl">Личный кабинет</h1>
        <p className="text-sm text-muted-foreground">Профиль, контакты и безопасность</p>
      </div>
      <Profile account={data} />
      <Contacts account={data} />
      {isPatient && <Channels account={data} />}
      <Password />
    </div>
  );
}

function Profile({ account }: { account: Account }) {
  const label = useLabels();
  const rows: [string, string][] = [
    ["ФИО", account.full_name],
    ["Роль", ROLE_LABELS[account.role]],
  ];
  if (account.specialty) rows.push(["Специальность", label("specialists", account.specialty)]);
  if (account.birth_date) rows.push(["Дата рождения", fmtDate(account.birth_date)]);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <UserRound className="size-5 text-primary" /> Профиль
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-2 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="grid grid-cols-[10rem_1fr] gap-2">
            <span className="text-muted-foreground">{k}</span>
            <span>{v}</span>
          </div>
        ))}
        {account.role !== "patient" && (
          <p className="mt-2 text-xs text-muted-foreground">
            ФИО и специальность меняет главный врач.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function Contacts({ account }: { account: Account }) {
  const update = useUpdateAccount();
  const isPatient = account.role === "patient";
  const [email, setEmail] = useState(account.email);
  const [phone, setPhone] = useState(account.phone ?? "");
  const [contactEmail, setContactEmail] = useState(account.contact_email ?? "");
  const dirty =
    email !== account.email ||
    (isPatient &&
      (phone !== (account.phone ?? "") || contactEmail !== (account.contact_email ?? "")));

  function submit(e: React.FormEvent) {
    e.preventDefault();
    update.mutate(isPatient ? { email, phone, contact_email: contactEmail } : { email }, {
      // Сервер нормализует email — показываем то, что сохранилось
      onSuccess: (a) => setContactEmail(a.contact_email ?? ""),
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Контакты</CardTitle>
      </CardHeader>
      <CardContent>
        <form className="grid gap-4" onSubmit={submit}>
          <Field id="email" label="Email (логин)">
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </Field>
          {isPatient && (
            <>
              <Field id="phone" label="Телефон">
                <Input
                  id="phone"
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  required
                />
              </Field>
              <Field id="contact-email" label="Email для уведомлений">
                <Input
                  id="contact-email"
                  type="email"
                  value={contactEmail}
                  placeholder={`не указан — на ${email}`}
                  onChange={(e) => setContactEmail(e.target.value)}
                />
              </Field>
            </>
          )}
          <Footer pending={update.isPending} disabled={!dirty} saved={update.isSuccess && !dirty}>
            {update.isError && errorMessage(update.error)}
          </Footer>
        </form>
      </CardContent>
    </Card>
  );
}

function Channels({ account }: { account: Account }) {
  const update = useUpdateAccount();
  const selected = new Set(account.notify_channels);

  function toggle(c: NotificationChannel) {
    const next = new Set(selected);
    if (next.has(c)) next.delete(c);
    else next.add(c);
    update.mutate({ notify_channels: CHANNELS.filter((x) => next.has(x)) });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Bell className="size-5 text-primary" /> Уведомления
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-2 text-sm">
        <p className="text-muted-foreground">
          Куда присылать рекомендации врача. В личном кабинете они появляются всегда.
        </p>
        {CHANNELS.map((c) => {
          const available = account.available_channels.includes(c);
          return (
            <label
              key={c}
              className={cn(
                "flex items-center gap-3 rounded-xl border bg-background p-3",
                available ? "cursor-pointer hover:border-primary/40" : "opacity-60",
              )}
            >
              <input
                type="checkbox"
                className="size-4 accent-primary"
                checked={available && selected.has(c)}
                disabled={!available || update.isPending}
                onChange={() => toggle(c)}
              />
              <span className="flex-1">{CHANNEL_LABELS[c]}</span>
              {!available && (
                <span className="text-xs text-muted-foreground">{CHANNEL_CONTACT[c]}</span>
              )}
            </label>
          );
        })}
        {update.isError && <p className="text-sm text-destructive">{errorMessage(update.error)}</p>}
      </CardContent>
    </Card>
  );
}

function Password() {
  const change = useChangePassword();
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    change.mutate(
      { old_password: oldPassword, new_password: newPassword },
      {
        onSuccess: () => {
          setOldPassword("");
          setNewPassword("");
        },
      },
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="size-5 text-primary" /> Пароль
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form className="grid gap-4" onSubmit={submit}>
          <Field id="old_password" label="Текущий пароль">
            <Input
              id="old_password"
              type="password"
              autoComplete="current-password"
              value={oldPassword}
              onChange={(e) => {
                change.reset();
                setOldPassword(e.target.value);
              }}
              required
            />
          </Field>
          <Field id="new_password" label="Новый пароль">
            <Input
              id="new_password"
              type="password"
              autoComplete="new-password"
              minLength={4}
              value={newPassword}
              onChange={(e) => {
                change.reset();
                setNewPassword(e.target.value);
              }}
              required
            />
          </Field>
          <Footer pending={change.isPending} saved={change.isSuccess} label="Сменить пароль">
            {change.isError && errorMessage(change.error)}
          </Footer>
        </form>
      </CardContent>
    </Card>
  );
}

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}

function Footer({
  pending,
  disabled,
  saved,
  label = "Сохранить",
  children,
}: {
  pending: boolean;
  disabled?: boolean;
  saved: boolean;
  label?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center justify-end gap-3">
      {children && <p className="mr-auto text-sm text-destructive">{children}</p>}
      {saved && !children && (
        <span className="inline-flex items-center gap-1 text-sm text-emerald-700">
          <Check className="size-4" /> Сохранено
        </span>
      )}
      <Button type="submit" disabled={pending || disabled}>
        {pending && <Loader2 className="animate-spin" />}
        {label}
      </Button>
    </div>
  );
}
