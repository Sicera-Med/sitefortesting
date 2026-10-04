"use client";

import { ChartColumn, Loader2, Stethoscope, User as UserIcon, UserCog } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { BrandLogo } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/api/client";
import { useDemoUsers } from "@/lib/api/hooks";
import type { DemoAccount, Role } from "@/lib/api/types";
import { homePath, useAuth } from "@/lib/auth";
import { useLabels } from "@/lib/format";

const GROUPS: { role: Role; title: string; icon: typeof UserIcon }[] = [
  { role: "doctor", title: "Врачи", icon: Stethoscope },
  { role: "chief", title: "Главный врач", icon: UserCog },
  { role: "manager", title: "Менеджер", icon: ChartColumn },
  { role: "patient", title: "Пациенты", icon: UserIcon },
];

export default function LoginPage() {
  const { user, login } = useAuth();
  const router = useRouter();
  const demo = useDemoUsers();
  const label = useLabels();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user) router.replace(homePath(user.role));
  }, [user, router]);

  async function signIn(e: string, p: string) {
    setPending(e);
    setError(null);
    try {
      const u = await login(e, p);
      router.replace(homePath(u.role));
    } catch (err) {
      setError(errorMessage(err));
      setPending(null);
    }
  }

  const byRole = (role: Role) => (demo.data ?? []).filter((a) => a.role === role);

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-4 pb-12">
      <header className="flex h-20 items-center">
        <BrandLogo />
      </header>

      <section className="grid gap-8 rounded-3xl bg-card p-8 md:grid-cols-[1.3fr_1fr] md:p-12">
        <div className="flex flex-col justify-center gap-5">
          <h1 className="text-4xl leading-[1.1] font-medium tracking-tight md:text-6xl">
            <span className="text-primary">AI-триаж</span>
            <br />
            медицинских заключений
          </h1>
          <p className="max-w-xl text-lg text-muted-foreground md:text-xl">
            Врач видит рекомендацию модели и принимает решение, пациент получает уведомление и
            записывается на приём, заведующий видит, насколько врачи согласны с AI.
          </p>
        </div>

        <form
          className="grid content-center gap-4 rounded-2xl bg-background p-6"
          onSubmit={(e) => {
            e.preventDefault();
            signIn(email, password);
          }}
        >
          <h2 className="text-xl font-medium">Вход</h2>
          <div className="grid gap-1.5">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="username"
              className="h-10"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="password">Пароль</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              className="h-10"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <Button type="submit" size="lg" className="h-11 text-base" disabled={!!pending}>
            {pending === email && <Loader2 className="animate-spin" />}
            Войти
          </Button>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </form>
      </section>

      <section className="grid gap-6 rounded-3xl bg-card p-8 md:p-12">
        <div>
          <h2 className="text-3xl font-medium tracking-tight md:text-4xl">
            <span className="text-muted-foreground">Быстрый</span> вход
          </h2>
          <p className="mt-1 text-muted-foreground">Демо-аккаунты, пароль у всех — demo</p>
        </div>
        {demo.isLoading && <Loader2 className="mx-auto animate-spin text-muted-foreground" />}
        {demo.isError && <p className="text-sm text-destructive">{errorMessage(demo.error)}</p>}
        {GROUPS.map(({ role, title, icon: Icon }) => {
          const accounts = byRole(role);
          if (!accounts.length) return null;
          return (
            <div key={role} className="grid gap-3">
              <div className="flex items-center gap-2 text-lg font-medium">
                <Icon className="size-5 text-primary" /> {title}
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {accounts.map((a: DemoAccount) => (
                  <button
                    key={a.email}
                    type="button"
                    disabled={!!pending}
                    onClick={() => signIn(a.email, a.password)}
                    className="group flex items-center justify-between gap-2 rounded-2xl border border-transparent bg-background p-4 text-left transition-colors hover:border-primary/40 disabled:opacity-60"
                  >
                    <span className="grid">
                      <span className="font-medium">{a.full_name}</span>
                      <span className="text-sm text-muted-foreground">
                        {a.specialty ? label("specialists", a.specialty) : a.email}
                      </span>
                    </span>
                    {pending === a.email && (
                      <Loader2 className="size-4 shrink-0 animate-spin text-primary" />
                    )}
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </section>
    </div>
  );
}
