import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";

import { Providers } from "./providers";
import "./globals.css";

const sans = Inter({ variable: "--font-sans", subsets: ["latin", "cyrillic"] });
const mono = JetBrains_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin", "cyrillic"],
});

export const metadata: Metadata = {
  title: "Третье мнение — AI-триаж заключений",
  description:
    "Рекомендации AI по протоколам лучевых исследований: маршрут пациента со ссылками на клинические рекомендации",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ru" className={`${sans.variable} ${mono.variable} h-full antialiased`}>
      <body className="min-h-full bg-background font-sans">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
