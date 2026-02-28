# Verification: Autonomous FB Mode

Как убедиться, что autonomous FB режим работает корректно после настройки.

---

## Быстрая проверка (5 минут)

```bash
cd J:/Project_Vibe/i.il/apps/local-engine

# 1. Зависимости
python main.py --health

# 2. Один тестовый прогон
python main.py --proof-fb

# 3. Проверить результат в БД
python -c "
import sqlite3
db = sqlite3.connect('data/news_hub.db')
print('published:', db.execute(\"SELECT COUNT(*) FROM stories WHERE state='published'\").fetchone()[0])
print('fb_completed:', db.execute(\"SELECT COUNT(*) FROM publish_queue WHERE status='completed'\").fetchone()[0])
print('last 3 posts:')
for r in db.execute(\"SELECT s.story_id, s.title_ru, p.fb_post_id, p.fb_posted_at FROM stories s JOIN publications p ON p.story_id = s.story_id WHERE p.fb_status='completed' ORDER BY p.fb_posted_at DESC LIMIT 3\"):
    print(' ', dict(r))
"
```

---

## Детальная проверка по шагам

### 1. Проверка DB

```bash
python -c "
import sqlite3
db = sqlite3.connect('data/news_hub.db')

print('=== Database Stats ===')
print('items:    ', db.execute('SELECT COUNT(*) FROM items').fetchone()[0])
print('stories:  ', db.execute('SELECT COUNT(*) FROM stories').fetchone()[0])
print('published:', db.execute(\"SELECT COUNT(*) FROM stories WHERE state='published'\").fetchone()[0])
print('drafts:   ', db.execute(\"SELECT COUNT(*) FROM stories WHERE state='draft'\").fetchone()[0])
print()
print('=== Publications ===')
for r in db.execute('SELECT fb_status, COUNT(*) c FROM publications GROUP BY fb_status'):
    print(f'  {r[0]}: {r[1]}')
print()
print('=== Images ===')
for r in db.execute('SELECT status, COUNT(*) c FROM images_cache GROUP BY status'):
    print(f'  {r[0]}: {r[1]}')
"
```

**Ожидаемый результат после первого цикла:**
```
items:     150+
stories:   25+
published: 10+
drafts:    0 (все обработаны)
```

### 2. Проверка FB публикаций

```bash
python -c "
import sqlite3
db = sqlite3.connect('data/news_hub.db')

print('=== FB Queue Status ===')
for r in db.execute('SELECT status, COUNT(*) c FROM publish_queue WHERE channel=\"fb\" GROUP BY status'):
    print(f'  {r[0]}: {r[1]}')

print()
print('=== Last 5 FB Posts ===')
for r in db.execute('''
    SELECT s.story_id, LEFT(s.title_ru, 60) as title,
           p.fb_post_id, p.fb_posted_at
      FROM stories s
      JOIN publications p ON p.story_id = s.story_id
     WHERE p.fb_posted_at IS NOT NULL
     ORDER BY p.fb_posted_at DESC
     LIMIT 5
'''):
    print(f\"  [{r['fb_posted_at'][:19]}] {r['title']}\")
    print(f\"    post_id: {r['fb_post_id']}\")
"
```

**Что нужно увидеть:**
- `status='completed'` — посты успешно опубликованы
- `fb_post_id` — не NULL и содержит ID вида `123456789_987654321`

### 3. Проверка через FB Graph API

После proof run возьмите `fb_post_id` из БД и проверьте через API:

```bash
# Замените POST_ID и ACCESS_TOKEN на реальные значения
curl "https://graph.facebook.com/v21.0/POST_ID?access_token=ACCESS_TOKEN&fields=id,message,created_time"
```

**Ожидаемый ответ:**
```json
{
  "id": "123456789_987654321",
  "message": "Заголовок\n\nТекст резюме...\n\n#хэштеги",
  "created_time": "2026-02-28T10:30:00+0000"
}
```

### 4. Проверка логов

```bash
# Посмотреть последний цикл
tail -50 data/logs/engine.jsonl | python -m json.tool 2>/dev/null | grep -A2 '"fb_done"'

# Должны увидеть:
# "event": "fb_done"
# "posted": 3    ← количество постов
# "failed": 0
# "rate_limited": 0
```

### 5. Проверка rate state

```bash
python -c "
import sqlite3
db = sqlite3.connect('data/news_hub.db')
r = db.execute('SELECT * FROM fb_rate_state WHERE id=1').fetchone()
if r:
    print('posts_this_hour:', r['posts_this_hour'])
    print('posts_today:    ', r['posts_today'])
    print('last_post_at:   ', r['last_post_at'])
else:
    print('No rate state (no posts yet)')
"
```

---

## Проверка daemon режима

После запуска `python main.py --loop`:

```bash
# Убедиться, что процесс запущен
tasklist /fi "imagename eq python.exe"

# Следить за циклами в реальном времени
tail -f data/logs/engine.jsonl | grep -E '"(cycle_start|cycle_done|fb_done|summary_done)"'
```

**Ожидаемый паттерн каждые 10 минут:**
```
{"event": "cycle_start", "run_id": "a1b2c3d4", ...}
{"event": "source_ok", "source": "ynet", "found": 30, "new": 5, ...}
...
{"event": "summary_done", "attempted": 3, "published": 3, ...}
{"event": "images_done", "downloaded": 3, ...}
{"event": "fb_done", "posted": 2, "failed": 0, ...}
{"event": "cycle_done", "items_new": 5, "fb_posts": 2, ...}
```

---

## Проверка Task Scheduler

```powershell
# Статус задачи
Get-ScheduledTask -TaskName "NewsHubEngineAutonomous" | Select-Object TaskName, State

# История запусков (последние 10)
Get-WinEvent -LogName "Microsoft-Windows-TaskScheduler/Operational" `
  -FilterXPath "*[EventData[Data[@Name='TaskName']='\NewsHubEngineAutonomous']]" `
  -MaxEvents 10 | Select-Object TimeCreated, Id, Message | Format-List
```

**Ожидаемый статус:** `Running` или `Ready`

---

## Чеклист полной верификации

- [ ] `python main.py --health` — все проверки `[OK  ]`
- [ ] `python main.py --proof-fb` — завершается с exit 0 и "PROOF PASSED"
- [ ] В БД: `publish_queue` содержит записи со `status='completed'`
- [ ] В БД: `publications` содержит `fb_post_id` (не NULL) для опубликованных историй
- [ ] В FB: посты реально видны на странице (проверить вручную)
- [ ] `python main.py --loop` запускается и выводит `cycle_done` каждые ~10 мин
- [ ] Task Scheduler: задача `NewsHubEngineAutonomous` создана и в статусе `Ready`/`Running`
- [ ] Логи пишутся в `data/logs/engine.jsonl` без ошибок уровня `error`

---

## Таблица ожидаемых метрик (первые 24 часа)

| Метрика | Минимум | Норма |
|---------|---------|-------|
| Циклов выполнено | 100 | 140+ |
| Новых статей | 500 | 1500+ |
| Историй опубликовано | 50 | 150+ |
| FB постов отправлено | 20 | 40 |
| Ошибок total | 0 | < 10 |
| Rate limited срабатываний | 0 | < 5 |

---

Подробнее о настройке: [`docs/AUTONOMOUS_FB_SETUP.md`](AUTONOMOUS_FB_SETUP.md)
