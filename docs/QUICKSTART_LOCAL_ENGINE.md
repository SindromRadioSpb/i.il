# Quickstart: Local Engine

Пошаговый запуск `apps/local-engine` с нуля до первого цикла обработки новостей.

---

## Команды

Все команды запускаются из PowerShell в директории `J:\Project_Vibe\i.il\apps\local-engine`:

| Команда | Описание |
|---------|----------|
| `python main.py` | Один цикл: парсинг → кластеризация → резюме → FB → CF sync |
| `python main.py --loop` | Непрерывный режим (каждые 450 сек) |
| `python main.py --status` | Мгновенный дашборд состояния (без запуска цикла) |
| `python main.py --preview-fb` | Предпросмотр следующих 3 постов Facebook |
| `python main.py --preview-fb 5` | Предпросмотр следующих N постов Facebook |
| `python main.py --health` | Проверка доступности Ollama и конфигурации |

---

## Требования

| Компонент | Версия |
|-----------|--------|
| Python | 3.11+ |
| Ollama | 0.17+ |
| Модель | qwen2.5:7b-instruct (Q4_K_M) |

---

## Шаг 1 — Установить зависимости

```bash
cd J:/Project_Vibe/i.il/apps/local-engine
pip install -e ".[dev]"
```

Проверка:
```bash
python -c "import aiosqlite, httpx, feedparser, structlog, pydantic, PIL, bs4, numpy; print('OK')"
```

---

## Шаг 2 — Убедиться, что Ollama работает

```bash
ollama list
# должна быть строка: qwen2.5:7b-instruct
```

Если модели нет:
```bash
ollama pull qwen2.5:7b-instruct
```

Проверка API:
```bash
curl http://localhost:11434/api/tags
# {"models":[{"name":"qwen2.5:7b-instruct",...}]}
```

---

## Шаг 3 — Создать `.env`

```bash
cd J:/Project_Vibe/i.il/apps/local-engine
cp .env.example .env
```

Открыть `.env` и заполнить:

```bash
# ── Обязательно ──────────────────────────────────────────────
DATABASE_PATH=data/news_hub.db
SOURCES_REGISTRY_PATH=../../sources/registry.yaml

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b-instruct

# ── Рекомендуется для дебага ──────────────────────────────────
LOG_FORMAT=text          # читаемые логи вместо JSON
LOG_LEVEL=INFO

# ── Отключено по умолчанию (включать позже) ───────────────────
FB_POSTING_ENABLED=false
CF_SYNC_ENABLED=false
CF_SYNC_TOKEN=           # получить из wrangler secret
```

> Все остальные переменные уже имеют разумные значения по умолчанию.

---

## Шаг 4 — Проверить тесты

```bash
cd J:/Project_Vibe/i.il/apps/local-engine
python -m pytest tests/ -q
# Ожидается: 408 passed
```

---

## Шаг 5 — Запустить один цикл

```powershell
cd J:\Project_Vibe\i.il\apps\local-engine
python main.py
```

**Что должно произойти** (в порядке выполнения):

```
[info ] db_ready path=data/news_hub.db
[info ] starting_once_mode
[info ] sources_loaded total=8
[info ] cycle_start run_id=a1b2c3d4
[info ] source_ok source=ynet found=30 new=30
[info ] source_ok source=haaretz found=25 new=25
...
[info ] cluster_ok source=ynet stories_new=12 stories_updated=3
...
[info ] summary_done attempted=15 published=12 skipped=2 failed=1 elapsed_ms=42000
[info ] images_done downloaded=10 failed=2 elapsed_ms=8000
[info ] sync_skipped reason=CF_SYNC_ENABLED=false
[info ] cycle_done items_new=150 stories_new=25 published=12 errors=1
```

Первый запуск займёт ~5–10 минут: ~150 новых статей × 3 сек/резюме = много работы для Ollama.

---

## Шаг 6 — Проверить результат в базе данных

```bash
python -c "
import sqlite3
db = sqlite3.connect('data/news_hub.db')
print('items:    ', db.execute('SELECT COUNT(*) FROM items').fetchone()[0])
print('stories:  ', db.execute('SELECT COUNT(*) FROM stories').fetchone()[0])
print('published:', db.execute(\"SELECT COUNT(*) FROM stories WHERE state='published'\").fetchone()[0])
print('drafts:   ', db.execute(\"SELECT COUNT(*) FROM stories WHERE state='draft'\").fetchone()[0])
print('unsynced: ', db.execute(\"SELECT COUNT(*) FROM stories WHERE state='published' AND cf_synced_at IS NULL\").fetchone()[0])
print()
print('Последние 5 историй:')
for r in db.execute(\"SELECT story_id, title_ru, state, last_update_at FROM stories ORDER BY last_update_at DESC LIMIT 5\"):
    print(' ', r)
"
```

---

## Шаг 7 — Включить CF Sync (когда готов)

1. Получить токен из Worker:
```bash
# Токен задаётся в wrangler secret, либо смотреть в .env Worker
```

2. Добавить в `.env`:
```bash
CF_SYNC_ENABLED=true
CF_SYNC_TOKEN=ваш_токен_здесь
```

3. Запустить ещё один цикл:
```bash
python main.py
```

После этого все опубликованные истории появятся на сайте.

---

## Непрерывный режим (daemon)

```powershell
python main.py --loop
```

Запускает цикл каждые `SCHEDULER_INTERVAL_SEC` секунд (по умолчанию 450 = 7.5 минут).
Остановить: **Ctrl+C** — движок дождётся завершения текущего цикла и выйдет.

---

## Дашборд состояния

Мгновенный снимок состояния пайплайна — без запуска цикла:

```powershell
cd J:\Project_Vibe\i.il\apps\local-engine
python main.py --status
```

Пример вывода:
```
=== Pipeline Status ===
  Stories :  0 draft  /  9 published
  Format  :  9 WOW  /  0 legacy (no fb_caption)
  FB Queue:  2 pending  /  7 done  /  3 posted today
  CF Sync :  9 on site  /  0 waiting to sync
  Last run:  2026-03-01T14:32:00Z  pub=9  fb=3  errors=0
```

Поля:
| Поле | Описание |
|------|----------|
| Stories | Черновики / опубликованные истории |
| Format | WOW (fb_caption заполнен) vs legacy (старый формат, не постится) |
| FB Queue | Очередь Facebook: pending / завершённые / отправлено сегодня |
| CF Sync | Синхронизировано с Cloudflare / ждут синхронизации |
| Last run | Время, число опубликованных, Facebook-постов и ошибок |

---

## Предпросмотр очереди Facebook

Посмотреть следующие N постов без публикации:

```powershell
# Следующие 3 поста (по умолчанию)
python main.py --preview-fb

# Следующие 5 постов
python main.py --preview-fb 5
```

Пример вывода:
```
=== FB Preview (next 3 pending posts) ===

--- [1/3] story_id=abc123 ---
🔴 Три беспилотника «Хезболлы» уничтожены над Галилеей

Сегодня ночью в небе над Галилеей сработала воздушная тревога.
Система «Железный купол» перехватила три БПЛА...

https://www.ynet.co.il/news/...

--- [2/3] story_id=def456 ---
...
```

> Если в очереди нет постов — все истории либо уже опубликованы, либо не имеют `fb_caption`.

---

## Мониторинг логов в реальном времени

```bash
# Если LOG_FORMAT=json (продакшн)
tail -f data/logs/engine.jsonl | python -m json.tool

# Если LOG_FORMAT=text (дебаг) — уже читаемо в консоли

# Фильтровать только ошибки
tail -f data/logs/engine.jsonl | grep '"level":"error"'

# Смотреть только фазу summary
tail -f data/logs/engine.jsonl | grep '"summary'
```

---

## Диагностика частых проблем

### Нет новых резюме — summary_done attempted=0

Все истории уже в состоянии `published` или нет новых черновиков. Проверить:
```bash
python -c "
import sqlite3; db = sqlite3.connect('data/news_hub.db')
print('drafts:', db.execute(\"SELECT COUNT(*) FROM stories WHERE state='draft'\").fetchone()[0])
"
```

### Ошибка Ollama — Connection refused

Ollama не запущен:
```bash
ollama serve
# или
ollama list  # должно ответить без ошибки
```

### source_error — HTTP 403 / SSL error

Источник временно недоступен. Бэкофф включится автоматически.
Принудительно сбросить бэкофф для источника:
```bash
python -c "
import sqlite3; db = sqlite3.connect('data/news_hub.db')
db.execute(\"UPDATE source_state SET backoff_until=NULL, consecutive_failures=0 WHERE source_id='ynet'\")
db.commit()
"
```

### Истории не появляются на сайте

Использовать диагностический инструмент:
```python
import asyncio
from db.connection import get_db
from observe.why_not import why_not_published
from config.settings import Settings

async def check(story_id):
    s = Settings()
    async with get_db(s.database_path) as db:
        reasons = await why_not_published(db, story_id)
        if reasons:
            for r in reasons: print(' -', r)
        else:
            print('Всё OK — история должна быть видна')

asyncio.run(check("STORY_ID_ЗДЕСЬ"))
```

### images_done failed=N — картинки не кэшируются

Нормально для статей без `enclosure_url` и недоступных og:image. Не критично.

---

## Посмотреть дневной отчёт

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

## Структура данных в SQLite

```
data/
├── news_hub.db          # основная база данных
├── images/              # кэш изображений ({prefix}/{hash}.{ext})
└── logs/
    └── engine.jsonl     # ротируемые логи (10 MB × 5 файлов)
```

Подробная схема всех таблиц: [`docs/DB_SCHEMA_LOCAL.md`](DB_SCHEMA_LOCAL.md)

---

## Включить FB Posting

1. Добавить в `.env`:
```bash
FB_POSTING_ENABLED=true
FB_PAGE_ID=ваш_page_id
FB_PAGE_ACCESS_TOKEN=ваш_long_lived_token
```

2. Лимиты по умолчанию: 8 постов/час, 40/день, интервал 3 минуты.
3. Настроить в `.env` при необходимости: `FB_MAX_PER_HOUR`, `FB_MAX_PER_DAY`, `FB_MIN_INTERVAL_SEC`.

Подробнее: [`docs/FB_PUBLISHING_POLICY.md`](FB_PUBLISHING_POLICY.md)

---

## Автозапуск (Windows Task Scheduler)

1. **Пуск → Task Scheduler → Create Task**
2. **General:** `NewsHubEngine`, Run whether logged on or not, Run with highest privileges
3. **Triggers:** At startup → Repeat every 15 minutes
4. **Actions:**
   - Program: `C:\Python314\python.exe`
   - Arguments: `J:\Project_Vibe\i.il\apps\local-engine\main.py --loop`
   - Start in: `J:\Project_Vibe\i.il\apps\local-engine`
5. **Settings:** If task is already running → **Do not start a new instance**

Подробнее: [`docs/OPS_RUNBOOK_FULL_LOCAL.md`](OPS_RUNBOOK_FULL_LOCAL.md)

---

## LLM backend switch (`llamacpp`)

Local-engine now supports provider selection via `.env`:

```bash
LLM_PROVIDER=llamacpp
LLM_BASE_URL=http://localhost:8001/v1
LLM_MODEL=YOUR_MODEL_ID
LLM_TIMEOUT_SEC=300
LLM_MAX_RETRIES=2
LLM_JSON_MODE=strict
MAX_SUMMARIES_PER_RUN=10
```

Verification commands:

```bash
python main.py --health
python main.py --proof-fb
```

See full guide: `docs/LLM_BACKEND_LLAMA_CPP.md`.
