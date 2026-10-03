// fetch-клиент: JWT из localStorage, единый формат ошибок backend → ApiError.

import type { ApiErrorBody } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

const TOKEN_KEY = "triage.token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // приватный режим — живём без сохранения
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
    public requestId?: string | null,
  ) {
    super(message);
  }
}

// Вызывается при 401 — AuthProvider подписывается и разлогинивает.
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

type Query = Record<string, string | number | string[] | undefined | null>;

function buildUrl(path: string, query?: Query) {
  const url = new URL(API_URL + path);
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v == null) continue;
    if (Array.isArray(v)) v.forEach((item) => url.searchParams.append(k, item));
    else url.searchParams.set(k, String(v));
  }
  return url.toString();
}

export async function api<T>(
  path: string,
  opts: { method?: string; body?: unknown; query?: Query } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(buildUrl(path, opts.query), {
      method: opts.method ?? "GET",
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    throw new ApiError(0, "network_error", "Сервер недоступен. Запущен ли backend?");
  }

  const requestId = res.headers.get("X-Request-ID");
  if (res.ok) {
    return (res.status === 204 ? undefined : await res.json()) as T;
  }

  let body: ApiErrorBody | null = null;
  try {
    body = await res.json();
  } catch {
    // не JSON — оставляем общий текст
  }
  if (res.status === 401 && token) onUnauthorized?.();
  throw new ApiError(
    res.status,
    body?.error?.code ?? "http_error",
    body?.error?.message ?? `Ошибка ${res.status}`,
    body?.error?.details,
    requestId,
  );
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Неизвестная ошибка";
}
