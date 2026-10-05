import type { NextConfig } from "next";

// Браузер ходит в API через сам сайт (/api/* → backend): один порт, без CORS, сайт открывается
// с телефона по адресу ноутбука. Адрес backend для прокси читается при сборке (next build)
const BACKEND_URL = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone", // для Docker: .next/standalone/server.js без node_modules
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
  experimental: {
    // По умолчанию прокси обрывает запрос через 30 с, а модель AI отвечает до 2 минут
    // (AI_TIMEOUT_S=120 на backend) — даём запас
    proxyTimeout: 180_000,
  },
};

export default nextConfig;
