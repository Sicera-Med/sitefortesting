// Логотип заказчика («Третье мнение») + название продукта.

import { cn } from "@/lib/utils";

export function BrandLogo({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-3", className)}>
      {/* eslint-disable-next-line @next/next/no-img-element -- статичный SVG, оптимизация не нужна */}
      <img src="/logo-third-opinion.svg" alt="Третье мнение" className="h-9 w-auto" />
      <span className="hidden border-l border-border pl-3 text-sm leading-tight text-muted-foreground sm:block">
        AI-триаж
        <br />
        заключений
      </span>
    </span>
  );
}
