"""Нагрузочное тестирование backend без AI: врачи, пациенты и менеджер работают одновременно.

Запуск (backend уже поднят; модель AI не вызывается — анализ в сценариях не участвует):

    uv run --project backend python scripts/loadtest.py --base http://localhost:8000 \\
        --users 10,50,100 --duration 30 --report docs/load-testing.md

Каждый уровень нагрузки — N виртуальных пользователей в пропорции врач : пациент : менеджер =
5 : 4 : 1. Каждый входит под демо-аккаунтом и по кругу выполняет свой сценарий до конца времени:
- врач: очередь → карточка → таймлайн; каждый 5-й круг — новое исследование из протокола
  и решение без AI (уведомление пациенту уходит автоматически — рассылки должны быть
  в режиме имитации, NOTIFY_REAL=false);
- пациент: уведомления → свободные слоты врача → запись → отмена;
- менеджер: дашборд метрик.

Ошибка — ответ 5xx или сетевой сбой. 409 при записи (слот успели занять) — нормальная
конкуренция за время врача, считается отдельно. Данные растут от уровня к уровню
(новые исследования), поэтому уровни идут от меньшего к большему.
"""

from __future__ import annotations

import argparse
import asyncio
import platform
import random
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

import httpx

DOCTORS = ["petrov", "sidorova", "kim"]
PATIENTS = ["ivanov", "kuznetsova", "popov", "vasilyeva", "sokolov",
            "morozova", "novikov", "fedorova", "volkov", "lebedeva"]  # fmt: skip
PASSWORD = "demo"

# Синтетический протокол КТ ОГК в формате «Поле- значение» (как на сайте заказчика)
SR = """Очаги и образования легких- не обнаружены
Грудная аорта- диаметр восходящего отдела 36 мм
Внутригрудные лимфоузлы- не увеличены
Плевральные полости- без выпота"""


@dataclass
class Stats:
    latencies: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    errors: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    conflicts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def record(self, name: str, ms: float, status: int | None) -> None:
        self.latencies[name].append(ms)
        if status is None or status >= 500:
            self.errors[name] += 1
        elif status == 409:
            self.conflicts[name] += 1


class User:
    def __init__(self, client: httpx.AsyncClient, stats: Stats) -> None:
        self.client = client
        self.stats = stats
        self.headers: dict[str, str] = {}

    async def call(self, name: str, method: str, url: str, **kw) -> httpx.Response | None:
        start = time.perf_counter()
        try:
            r = await self.client.request(method, url, headers=self.headers, **kw)
        except httpx.HTTPError:
            self.stats.record(name, (time.perf_counter() - start) * 1000, None)
            return None
        self.stats.record(name, (time.perf_counter() - start) * 1000, r.status_code)
        return r

    async def login(self, email: str) -> None:
        r = await self.call(
            "POST /auth/login", "POST", "/auth/login", json={"email": email, "password": PASSWORD}
        )
        if r is None or r.status_code != 200:
            raise RuntimeError(f"не удалось войти: {email}")
        self.headers = {"Authorization": f"Bearer {r.json()['access_token']}"}


async def doctor(u: User, key: str, deadline: float) -> None:
    await u.login(f"{key}@clinic.demo")
    patients = await u.call("GET /studies/patients", "GET", "/studies/patients")
    patient_ids = [p["id"] for p in patients.json()] if patients else []
    n = 0
    while time.monotonic() < deadline:
        n += 1
        r = await u.call("GET /studies", "GET", "/studies")
        studies = r.json() if r is not None and r.status_code == 200 else []
        if studies:
            sid = random.choice(studies)["id"]
            await u.call("GET /studies/{id}", "GET", f"/studies/{sid}")
            await u.call("GET /studies/{id}/audit", "GET", f"/studies/{sid}/audit")
        if n % 5 == 0 and patient_ids:
            body = {
                "patient_id": random.choice(patient_ids),
                "study_type": "ct",
                "body_region": "chest",
                "description": SR,
            }
            r = await u.call("POST /studies", "POST", "/studies", json=body)
            if r is not None and r.status_code == 200:
                decision = {"chosen_types": ["repeat_appointment"]}
                await u.call(
                    "POST /studies/{id}/decision",
                    "POST",
                    f"/studies/{r.json()['id']}/decision",
                    json=decision,
                )


async def patient(u: User, key: str, deadline: float, doctor_ids: list[str]) -> None:
    await u.login(f"{key}@patient.demo")
    while time.monotonic() < deadline:
        await u.call("GET /patients/me/notifications", "GET", "/patients/me/notifications")
        doctor_id = random.choice(doctor_ids)
        r = await u.call("GET /doctors/{id}/slots", "GET", f"/doctors/{doctor_id}/slots")
        days = r.json() if r is not None and r.status_code == 200 else []
        slots = [s for d in days for s in d["slots"]]
        if not slots:
            continue
        body = {"doctor_id": doctor_id, "scheduled_for": random.choice(slots)}
        r = await u.call("POST /appointments", "POST", "/appointments", json=body)
        if r is not None and r.status_code == 200:
            await u.call(
                "PATCH /appointments/{id}",
                "PATCH",
                f"/appointments/{r.json()['id']}",
                json={"status": "cancelled"},
            )


async def manager(u: User, deadline: float) -> None:
    await u.login("manager@clinic.demo")
    while time.monotonic() < deadline:
        await u.call("GET /metrics/dashboard", "GET", "/metrics/dashboard")


async def run_level(base: str, users: int, duration: float) -> tuple[Stats, float]:
    stats = Stats()
    limits = httpx.Limits(max_connections=users, max_keepalive_connections=users)
    async with httpx.AsyncClient(base_url=base, limits=limits, timeout=60) as client:
        probe = User(client, Stats())
        await probe.login("chief@clinic.demo")
        r = await probe.call("doctors", "GET", "/doctors")
        doctor_ids = [d["id"] for d in r.json()]

        deadline = time.monotonic() + duration
        tasks = []
        for i in range(users):
            u = User(client, stats)
            match i % 10:
                case 0:
                    tasks.append(manager(u, deadline))
                case 1 | 2 | 3 | 4:
                    tasks.append(patient(u, PATIENTS[i % len(PATIENTS)], deadline, doctor_ids))
                case _:
                    tasks.append(doctor(u, DOCTORS[i % len(DOCTORS)], deadline))
        start = time.monotonic()
        await asyncio.gather(*tasks)
        return stats, time.monotonic() - start


def pct(values: list[float], p: float) -> float:
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[int(p) - 1]


def table(stats: Stats, elapsed: float) -> tuple[str, dict[str, float]]:
    rows = [
        "| Запрос | Кол-во | RPS | p50, мс | p95, мс | p99, мс | Ошибки 5xx | 409 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    total = sum(len(v) for v in stats.latencies.values())
    every = [x for v in stats.latencies.values() for x in v]
    for name in sorted(stats.latencies):
        v = stats.latencies[name]
        rows.append(
            f"| `{name}` | {len(v)} | {len(v) / elapsed:.1f} | {pct(v, 50):.1f} | "
            f"{pct(v, 95):.1f} | {pct(v, 99):.1f} | {stats.errors[name]} | "
            f"{stats.conflicts[name]} |"
        )
    errors = sum(stats.errors.values())
    summary = {
        "requests": total,
        "rps": total / elapsed,
        "p50": pct(every, 50),
        "p95": pct(every, 95),
        "p99": pct(every, 99),
        "errors": errors,
    }
    rows.append(
        f"| **Всего** | {total} | {summary['rps']:.1f} | {summary['p50']:.1f} | "
        f"{summary['p95']:.1f} | {summary['p99']:.1f} | {errors} | "
        f"{sum(stats.conflicts.values())} |"
    )
    return "\n".join(rows), summary


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--users", default="10,50,100", help="уровни нагрузки через запятую")
    ap.add_argument("--duration", type=float, default=30, help="секунд на уровень")
    ap.add_argument("--report", help="записать отчёт в markdown-файл")
    args = ap.parse_args()
    base = args.base.rstrip("/") + "/api/v1"
    levels = [int(x) for x in args.users.split(",")]

    sections, summaries = [], []
    for users in levels:
        print(f"→ {users} пользователей, {args.duration:.0f} с …", flush=True)
        stats, elapsed = await run_level(base, users, args.duration)
        text, summary = table(stats, elapsed)
        print(text, "\n", flush=True)
        sections.append(f"### {users} одновременных пользователей\n\n{text}\n")
        summaries.append((users, summary))

    head = [
        "| Пользователей | Запросов | RPS | p50, мс | p95, мс | p99, мс | Ошибки |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    head += [
        f"| {u} | {s['requests']} | {s['rps']:.1f} | {s['p50']:.1f} | {s['p95']:.1f} | "
        f"{s['p99']:.1f} | {s['errors']} |"
        for u, s in summaries
    ]
    if args.report:
        env = (
            f"{datetime.now():%Y-%m-%d %H:%M}, {platform.system()} {platform.machine()}, "
            f"Python {platform.python_version()}, {args.duration:.0f} с на уровень, "
            f"генератор нагрузки на той же машине"
        )
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(
                "## Результаты прогона\n\n"
                f"Стенд: {env}.\n\n" + "\n".join(head) + "\n\n" + "\n".join(sections)
            )
        print(f"Отчёт: {args.report}")


if __name__ == "__main__":
    asyncio.run(main())
