"use client";

import { useTheme } from "next-themes";
import { useEffect } from "react";
import { Toaster as Sonner, type ToasterProps } from "sonner";
import {
  CircleCheckIcon,
  InfoIcon,
  TriangleAlertIcon,
  OctagonXIcon,
  Loader2Icon,
} from "lucide-react";

const Toaster = ({ ...props }: ToasterProps) => {
  const { theme = "system" } = useTheme();

  // Закрытие по клику в любом месте тоста (на ПК смахивать неудобно):
  // нажимаем штатную кнопку закрытия — так сохраняется анимация исчезновения.
  // Перетаскивание кликом не считаем: Sonner захватывает указатель, и click всё равно придёт.
  useEffect(() => {
    let down: { x: number; y: number } | null = null;
    function onPointerDown(e: PointerEvent) {
      down = { x: e.clientX, y: e.clientY };
    }
    function onClick(e: MouseEvent) {
      const target = e.target as HTMLElement;
      const toast = target.closest("[data-sonner-toast]");
      if (!toast || target.closest("button")) return;
      if (down && Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5) return;
      toast.querySelector<HTMLButtonElement>("[data-close-button]")?.click();
    }
    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("click", onClick);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("click", onClick);
    };
  }, []);

  return (
    <Sonner
      theme={theme as ToasterProps["theme"]}
      swipeDirections={[]}
      closeButton
      className="toaster group"
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        error: <OctagonXIcon className="size-4" />,
        loading: <Loader2Icon className="size-4 animate-spin" />,
      }}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius)",
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          toast: "cn-toast cursor-pointer",
        },
      }}
      {...props}
    />
  );
};

export { Toaster };
