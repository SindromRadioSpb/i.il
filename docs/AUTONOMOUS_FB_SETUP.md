# Autonomous FB Setup Guide

Пошаговое руководство по настройке автономного режима с публикацией в Facebook.

---

## Требования

| Компонент | Статус |
|-----------|--------|
| `apps/local-engine` установлен и тесты проходят | обязательно |
| Ollama запущен (`ollama serve`) | обязательно |
| FB Page с правами `pages_manage_posts` | обязательно |
| Long-lived Page Access Token | обязательно |

---

## Шаг 1 — Получить FB Page Access Token

1. Откройте [Facebook Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. Выберите своё приложение → добавьте разрешения: `pages_manage_posts`, `pages_read_engagement`
3. Нажмите **Generate Access Token** → скопируйте краткосрочный токен
4. Обменяйте на долгосрочный (действует 60 дней):

```bash
curl "https://graph.facebook.com/v21.0/oauth/access_token
  ?grant_type=fb_exchange_token
  &client_id=YOUR_APP_ID
  &client_secret=YOUR_APP_SECRET
  &fb_exchange_token=SHORT_LIVED_TOKEN"
```

5. Получите Page Token (от имени страницы, не пользователя):

```bash
curl "https://graph.facebook.com/v21.0/me/accounts?access_token=LONG_LIVED_USER_TOKEN"
# Найдите нужную страницу и скопируйте её access_token
```

---

## Шаг 2 — Настроить `.env`

```bash
cd J:/Project_Vibe/i.il/apps/local-engine
cp .env.example .env
```

Заполните обязательные поля:

```bash
# ── Facebook ──────────────────────────────────────────────────────────────
FB_POSTING_ENABLED=true
FB_PAGE_ID=123456789012345
FB_PAGE_ACCESS_TOKEN=EAAxxxxxxxxx...

# Лимиты (рекомендуемые значения)
FB_MAX_PER_HOUR=8
FB_MAX_PER_DAY=40
FB_MIN_INTERVAL_SEC=180

# ── Proof Mode ────────────────────────────────────────────────────────────
# Для тестирования перед запуском daemon-режима
FB_PROOF_MODE=false                  # активируется автоматически при --proof-fb
FB_PROOF_MAX_POSTS_PER_RUN=3         # сколько постов в тестовом прогоне
FB_PROOF_REQUIRE_IMAGE=true          # постить только истории с изображениями
FB_PROOF_ONLY_CATEGORY=              # оставьте пустым = любая категория
```

---

## Шаг 3 — Проверить зависимости (`--health`)

```bash
cd J:/Project_Vibe/i.il/apps/local-engine
python main.py --health
```

Ожидаемый вывод (все `[OK  ]`):

```
=== Health Check ===
  [OK  ] DB           data/news_hub.db
  [OK  ] Ollama       reachable, model found
  [OK  ] Sources      8 enabled
  [OK  ] FB Token     page_id=123456789012345, token present
  [OK  ] CF Sync      CF sync disabled — skipped
===================
All checks passed.
```

Если какая-то проверка показывает `[FAIL]` — устраните проблему до следующего шага.

---

## Шаг 4 — Запустить Proof Run (`--proof-fb`)

Proof run выполняет один цикл с ограничением по количеству постов и завершается:
- **exit 0** — если было опубликовано ≥ 2 поста (тест пройден)
- **exit 1** — если опубликовано < 2 (нужна диагностика)

```bash
python main.py --proof-fb
```

**Что происходит во время proof run:**

1. Ingest: скачивает свежие новости из всех включённых источников
2. Summary: генерирует русские резюме для новых историй (через Ollama)
3. Images: кэширует изображения для опубликованных историй
4. FB: публикует до `FB_PROOF_MAX_POSTS_PER_RUN` постов в Facebook
   - Если `FB_PROOF_REQUIRE_IMAGE=true` — публикуются только истории с изображениями
   - Если `FB_PROOF_ONLY_CATEGORY` задан — только истории этой категории
5. CF Sync: (если включён) синхронизирует истории с Cloudflare

**Пример успешного вывода:**

```
=== PROOF RUN SUMMARY ===
  Items new:      147
  Stories new:    23
  Summaries pub:  18
  FB posts sent:  3
  Errors:         0
=========================
PROOF PASSED: 3 FB posts sent successfully.
```

**Пример провала:**

```
=== PROOF RUN SUMMARY ===
  Items new:      0
  Stories new:    0
  Summaries pub:  0
  FB posts sent:  0
  Errors:         2
=========================
PROOF FAILED: only 0/2 posts sent. Check logs for details.
```

При провале см. раздел [Диагностика](#диагностика).

---

## Шаг 5 — Запустить daemon-режим

После успешного proof run включите непрерывный режим:

```bash
python main.py --loop
```

Движок будет запускать цикл каждые `SCHEDULER_INTERVAL_SEC` секунд (по умолчанию 600 = 10 минут).
Остановить: **Ctrl+C** — движок дождётся завершения текущего цикла.

---

## Автозапуск при старте Windows (Task Scheduler)

### Быстрый способ — PowerShell-скрипт

```powershell
# Запустить от имени администратора
J:\Project_Vibe\i.il\scripts\windows\create_task_scheduler_autonomous.ps1
```

Скрипт создаст задачу `NewsHubEngineAutonomous` в Task Scheduler:
- Запускается при старте системы
- Повторяется каждые 15 минут (на случай сбоя)
- Настроено: «Не запускать новый экземпляр, если уже работает»

### Ручная настройка

1. **Пуск → Task Scheduler → Create Task**
2. **General:**
   - Name: `NewsHubEngineAutonomous`
   - Security options: Run whether logged on or not
   - Run with highest privileges: ✓
3. **Triggers:**
   - At startup (задержка 2 минуты)
   - Repeat every: 15 minutes indefinitely
4. **Actions:**
   - Program: `C:\Python314\python.exe`
   - Arguments: `J:\Project_Vibe\i.il\apps\local-engine\main.py --loop`
   - Start in: `J:\Project_Vibe\i.il\apps\local-engine`
5. **Settings:**
   - If task is already running: **Do not start a new instance**
   - Stop task if it runs longer than: 12 hours

---

## Диагностика

### proof run: FB posts sent = 0

**1. Нет опубликованных историй с изображениями:**
```bash
python -c "
import sqlite3
db = sqlite3.connect('data/news_hub.db')
print('published with image:', db.execute('''
  SELECT COUNT(*) FROM stories s
  WHERE s.state = 'published'
  AND EXISTS (SELECT 1 FROM images_cache ic
              WHERE ic.story_id = s.story_id AND ic.status = 'downloaded')
''').fetchone()[0])
print('published total:', db.execute(\"SELECT COUNT(*) FROM stories WHERE state='published'\").fetchone()[0])
"
```

Если `published total = 0` — нужно сначала запустить `python main.py` (без флагов) чтобы ingestion и summary заработали.

Если `published with image = 0` при ненулевом `published total`:
```bash
# Отключить требование к изображению для proof run
FB_PROOF_REQUIRE_IMAGE=false python main.py --proof-fb
```

**2. FB_STATUS уже не 'disabled':**
```bash
python -c "
import sqlite3
db = sqlite3.connect('data/news_hub.db')
print('fb_status counts:')
for r in db.execute(\"SELECT fb_status, COUNT(*) FROM publications GROUP BY fb_status\"):
    print(' ', r[0], ':', r[1])
"
```

Если все в `'pending'` или `'completed'` — нечего публиковать. Проверьте что summary pipeline работает.

**3. Ошибка авторизации FB (auth error 190/102):**

Токен истёк. Получите новый токен (Шаг 1) и обновите `.env`.

Проверьте последние ошибки:
```bash
python -c "
import sqlite3
db = sqlite3.connect('data/news_hub.db')
for r in db.execute(\"SELECT phase, code, message, created_at FROM error_events ORDER BY created_at DESC LIMIT 10\"):
    print(r)
"
```

**4. Rate limit активен:**
```bash
python -c "
import sqlite3
db = sqlite3.connect('data/news_hub.db')
r = db.execute('SELECT * FROM fb_rate_state WHERE id=1').fetchone()
if r:
    print(dict(r))
else:
    print('No rate state yet')
"
```

Сбросить rate state (использовать осторожно!):
```bash
python -c "
import sqlite3
db = sqlite3.connect('data/news_hub.db')
db.execute('DELETE FROM fb_rate_state')
db.commit()
print('Rate state cleared')
"
```

### Ollama недоступен

```bash
ollama serve
# или проверить статус:
ollama list
```

---

## Мониторинг

### Логи в реальном времени

```bash
# JSON формат (production)
tail -f data/logs/engine.jsonl | python -m json.tool

# Только FB события
tail -f data/logs/engine.jsonl | grep '"fb_'

# Только ошибки
tail -f data/logs/engine.jsonl | grep '"level":"error"'
```

### Дневной отчёт

```python
import asyncio
from db.connection import get_db
from observe.report import generate_daily_report
from config.settings import Settings

async def report():
    s = Settings()
    async with get_db(s.database_path) as db:
        md = await generate_daily_report(db, "2026-02-28")
        print(md)

asyncio.run(report())
```

---

## Лимиты FB по умолчанию

| Параметр | Значение | Переменная |
|----------|----------|------------|
| Постов в час | 8 | `FB_MAX_PER_HOUR` |
| Постов в день | 40 | `FB_MAX_PER_DAY` |
| Минимальный интервал | 3 мин | `FB_MIN_INTERVAL_SEC` |
| Попыток на пост | 5 | (в коде, не конфигурируется) |
| Бэкофф (ошибка) | до 1 часа | (экспоненциальный) |

Подробнее: [`docs/FB_PUBLISHING_POLICY.md`](FB_PUBLISHING_POLICY.md)
