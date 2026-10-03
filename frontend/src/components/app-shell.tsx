"use client";

import { Loader2, LogOut } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { BrandLogo } from "@/components/brand";
import { Button } from "@/components/ui/button";
import type { Role } from "@/lib/api/types";
import { homePath, useAuth } from "@/lib/auth";
import { ROLE_LABELS, useLabels } from "@/lib/format";
import { cn } from "@/lib/utils";

const NAV: Record<Role, { href: string; label: string }[]> = {
  doctor: [{ href: "/studies", label: "Мои исследования" }],
  head: [
    { href: "/dashboard", label: "Дашборд" },
    { href: "/studies", label: "Исследования" },
  ],
  patient: [{ href: "/patient", label: "Мой кабинет" }],
};

function FullScreenSpinner() {
  return (
    <div className="grid min-h-screen place-items-center">
      <Loader2 className="size-6 animate-spin text-muted-foreground" />
    </div>
  );
}

/** Шапка + проверка входа. Страница передаёт роли, которым она доступна. */
export function AppShell({ roles, children }: { roles: Role[]; children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const label = useLabels();

  const allowed = !!user && roles.includes(user.role);

  useEffect(() => {
    if (loading) return;
    if (!user) router.replace("/login");
    else if (!roles.includes(user.role)) router.replace(homePath(user.role));
  }, [user, loading, roles, router]);

  if (!allowed) return <FullScreenSpinner />;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-border/60 bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-16 w-full max-w-7xl items-center gap-8 px-4">
          <Link href={homePath(user.role)}>
            <BrandLogo />
          </Link>
          <nav className="flex gap-1">
            {NAV[user.role].map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "rounded-full px-4 py-2 text-[15px] text-foreground transition-colors hover:text-primary",
                  pathname.startsWith(item.href) && "bg-accent text-accent-foreground",
                )}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <div className="hidden text-right text-sm leading-tight sm:block">
              <div className="font-medium">{user.full_name}</div>
              <div className="text-xs text-muted-foreground">
                {user.specialty ? label("specialists", user.specialty) : ROLE_LABELS[user.role]}
              </div>
            </div>
            <Button variant="ghost" size="icon" onClick={logout} title="Выйти">
              <LogOut />
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8">{children}</main>
    </div>
  );
}
