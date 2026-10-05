# REST API backend

Префикс `/api/v1`. Авторизация — `Authorization: Bearer <JWT>` из `POST /auth/login`, кроме отмеченных «—». Интерактивная документация со схемами — Swagger: http://localhost:8000/docs.

**Ошибки** приходят в одном формате: `{"error": {"code", "message", "details"}}`.

| Код | Когда |
|---|---|
| `403` | нет прав |
| `404` | не найдено |
| `409` | конфликт: недопустимый переход статуса, слот занят, решение уже принято |
| `422` | неверные данные |
| `429` | слишком часто; в `details.retry_after_s` — через сколько секунд можно повторить |
| `502` | AI-сервис не ответил |

У каждого ответа есть заголовок `X-Request-ID`. Примеры запросов — [../examples/api.http](../examples/api.http).

Роли: `doctor` — врач, `chief` — главврач, `manager` — менеджер, `patient` — пациент. «Лечащий» — лечащий врач этого исследования.

## Вход и профиль

| Метод | Путь | Роли | Что делает |
|---|---|---|---|
| POST | `/auth/login` | — | `{email, password}` → `{access_token, user}` |
| GET | `/auth/me` | все | текущий пользователь |
| GET | `/auth/demo-users` | — | демо-аккаунты для быстрого входа (не в `APP_ENV=prod`) |
| GET / PATCH | `/account` | все | профиль; контакты (email, у пациента — телефон, email для уведомлений, соцсети, каналы) |
| POST | `/account/password` | все | смена пароля |

## Исследования (врач, главврач, менеджер)

| Метод | Путь | Роли | Что делает |
|---|---|---|---|
| GET | `/studies` | doctor, chief, manager | очередь: `?scope=mine\|all`, `?status=…` |
| POST | `/studies` | doctor, chief | новое исследование из DICOM SR: `{patient_id, study_type, body_region, description, conclusion?, performed_at?, treating_doctor_id?}` |
| GET | `/studies/patients` | doctor, chief, manager | пациенты для формы «Новое исследование» |
| GET | `/studies/{id}` | doctor, chief, manager | карточка: протокол, последний ответ AI, решение, уведомление, записи, направления |
| POST | `/studies/{id}/analyze` | лечащий, chief | отправить в AI; не чаще раза в 10 с (`429`) |
| POST | `/studies/{id}/decision` | лечащий, chief | `{chosen_types, details, comment?}` → решение; уведомление пациенту уходит автоматически |
| POST | `/studies/{id}/reassign` | chief | сменить лечащего врача до решения |
| POST | `/studies/{id}/ai-result` | лечащий, chief | запасной путь: загрузить ответ AI вручную (JSON по контракту) |
| GET | `/studies/{id}/history` | doctor, chief, manager | все ответы AI по исследованию |
| GET | `/studies/{id}/audit` | doctor, chief, manager | таймлайн действий |
| POST | `/ai/test` | doctor, chief, manager | прогнать текст через AI без сохранения (для AI-команды) |
| GET | `/ai/models` | doctor, chief, manager | модель текущего провайдера |

## Пациент

| Метод | Путь | Роли | Что делает |
|---|---|---|---|
| GET | `/patients/me/notifications` | patient | рекомендации врача, направления, записи |
| GET | `/patients/me/studies` | patient | свои исследования и решения, без протокола |
| POST | `/notifications/{id}/read` | patient (своё) | прочитано |
| POST | `/notifications/{id}/decline` | patient (своё) | отказ от рекомендации — кейс закрывается |
| POST | `/notifications/{id}/explain` | patient (своё) | объяснение заключения простым языком (AI, один раз) |
| POST | `/notifications/{id}/remind` | лечащий, chief | «Напомнить сейчас»: следующее напоминание сразу, до трёх |

## Запись

| Метод | Путь | Роли | Что делает |
|---|---|---|---|
| GET | `/doctors` | все | врачи, `?specialty=` |
| GET | `/doctors/{id}/slots` | все | свободное время врача по дням: `?start=YYYY-MM-DD&days=7` |
| GET | `/research/{code}/slots` | все | свободное время кабинета исследования |
| GET | `/appointments` | patient (свои), doctor (к нему), chief (`?doctor_id=`) | записи |
| POST | `/appointments` | patient | `{doctor_id \| research_type, scheduled_for, notification_id?, requirement?}` |
| PATCH | `/appointments/{id}` | patient (свои), doctor (к нему) | `{status: "cancelled"}` |

## Руководство

| Метод | Путь | Роли | Что делает |
|---|---|---|---|
| GET | `/metrics/dashboard` | manager | все метрики одним ответом |
| GET / POST / PATCH | `/staff/doctors[/{id}]` | chief | врачи с нагрузкой; добавить; изменить или отключить |

## Справочники и служебное

| Метод | Путь | Роли | Что делает |
|---|---|---|---|
| GET | `/dictionaries` | — | типы рекомендаций, специалисты, исследования, типы исследований, области — `[{code, label}]` |
| GET | `/health`, `/version` | — | проверка живости, версия |

## Метрики дашборда

| Метрика | Расчёт |
|---|---|
| Согласие с AI | решения, где вариант AI среди выбранных врачом / все решения, принятые при ответе AI |
| Совпадение деталей | среди совпавших по типу — совпали ли специалисты и исследования |
| Матрица «AI ↔ врач» 5×5 | строка — рекомендация AI, столбец — каждое выбранное врачом направление |
| По врачам | решений, согласие, совпадение деталей по каждому врачу |
| Воронка | уведомление отправлено → прочитано → записался хоть по одному → по всем; отказы отдельно |
| AI | число прогонов, ошибки, среднее и p95 времени ответа |
