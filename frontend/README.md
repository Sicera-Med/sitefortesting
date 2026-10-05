# frontend — сайт «Третье мнение: AI-триаж»

Next.js 16 (App Router), React 19, TanStack Query, shadcn/ui на Base UI, Tailwind 4. Общее описание
проекта и запуск всего стенда — в [корневом README](../README.md).

```bash
npm install
npm run dev        # http://localhost:3000, API проксируется на http://localhost:8000
npx tsc --noEmit && npx eslint src && npx prettier --check src
npm run build      # standalone-сборка для Docker (Dockerfile)
```

- `src/app/` — страницы по ролям: `studies` (врач), `dashboard` (менеджер), `doctors` (главврач),
  `patient` (пациент), `account`, `login`
- `src/components/` — интерфейс: `study/` (карточка исследования), `patient/` (кабинет и запись),
  `dashboard/`, `ui/` (shadcn)
- `src/lib/api/` — клиент API (`client.ts`), типы ответов backend (`types.ts`), запросы (`hooks.ts`)
- Адрес backend для прокси `/api/*` — `BACKEND_INTERNAL_URL` при сборке (`next.config.ts`)
