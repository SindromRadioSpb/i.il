# WOW-Story FB Post Format

Replaces the rigid 5-section `Что произошло / Почему важно / Что дальше` format
with an organic, engagement-optimised **mini-story** suitable for Facebook.

---

## Structure

```
[Line 1]  Hook headline — ≤90 chars, no duplication in body

[Body]    3–5 sentences, 450–900 chars total:
            Sentence 1 — scene/context (location, time)
            Sentences 2–3 — factual core (who, what, numbers preserved)
            Sentence 4 — contrast/implication; "по данным источников"
                         or "сообщают издания" REQUIRED if risk_level=high
            Sentence 5 — one short question to audience (no ragebait)

[Last line]  "Подробнее → <story_url>"
```

**No hashtags. No section labels. No invented facts.**

---

## 3-Pass LLM Pipeline

| Pass | Module | Input | Output |
|------|--------|-------|--------|
| 1 — Fact Extract | `summary/fact_extract.py` | Hebrew titles + snippets | `ExtractedFacts` JSON |
| 2 — Draft Post | `summary/wow_story.py` | `ExtractedFacts` JSON | Draft FB caption |
| 3 — Critic/Rewrite | `summary/wow_story.py` | Draft + violations list | Corrected caption |

Pass 3 reruns up to 2 times if guards fail. After 2 failed rewrites the
caption is discarded and the story is published with the **legacy fallback**
(title + 5-section summary_ru) until the next pipeline run.

---

## ExtractedFacts Schema

```json
{
  "event_type": "security|politics|economy|society|sport|other",
  "location": "string or null",
  "time_ref": "string or null",
  "actors": ["list of named persons/organizations"],
  "numbers": ["EVERY number/percentage/amount from titles"],
  "claims": ["facts EXPLICITLY in source titles"],
  "uncertainty_notes": ["anything ambiguous or unconfirmed"],
  "sources": ["source IDs"],
  "risk_level": "low|medium|high",
  "story_url": "caller-controlled URL (verbatim in post)"
}
```

`story_url` and `risk_level` are **always set by the caller** — the LLM
output for these fields is ignored.

---

## Guards (all must pass before posting)

| Guard | Rule |
|-------|------|
| `guard_wow_no_sections` | No section headers (`Что произошло:`, etc.) |
| `guard_wow_no_hashtags` | No `#word` hashtags |
| `guard_wow_no_duplicate_headline` | First line not repeated verbatim in body |
| `guard_wow_hallucination` | `ожидается/собираются/планируют/намерены` banned unless in `claims` |
| `guard_wow_high_risk_attribution` | `risk_level=high` → must contain `по данным источников` or `сообщают издания` |
| `guard_wow_numbers` | Every number in `ExtractedFacts.numbers` must appear in the post |
| `guard_wow_ends_with_url` | Last line must contain `story_url` |
| `guard_wow_length` | Total post: 450–1100 chars |
| `guard_wow_forbidden_words` | No `ужас`, `кошмар`, `шок`, `сенсация`, `скандал века` |

---

## Examples

### Example 1 — Security

**Input titles (Hebrew):**
```
1. [ynet] 3 כטבמ"מ של חיזבאללה יורטו מעל הגליל
2. [mako] יירוט מוצלח: מערכת כיפת ברזל בפעולה בצפון
```

**fb_caption:**
```
Три беспилотника «Хезболлы» уничтожены над Галилеей

Сегодня ночью в небе над Галилеей произошла воздушная тревога.
Система «Железный купол» успешно перехватила три БПЛА, запущенных
«Хезболлой» с ливанской территории, — сообщают издания.
Жертв и разрушений нет.

Насколько, по-вашему, реальна угроза с Севера сейчас?

Подробнее → https://www.ynet.co.il/news/article/xyz123
```

---

### Example 2 — Politics

**Input titles (Hebrew):**
```
1. [haaretz] הכנסת אישרה את תקציב המדינה ב-64 קולות בעד
2. [israelhayom] נאספו 64 קולות לאישור התקציב בקריאה שנייה
```

**fb_caption:**
```
Кнессет утвердил госбюджет: 64 голоса «за»

В четверг вечером Кнессет принял государственный бюджет во втором чтении.
За проголосовали 64 депутата из 120.
Принятие бюджета прерывает несколько месяцев политического кризиса.
Оппозиция заявила о намерении обжаловать ряд статей в Верховном суде.

Считаете ли вы, что это хороший бюджет для обычных граждан?

Подробнее → https://www.haaretz.co.il/news/politics/abc456
```

---

### Example 3 — Sport

**Input titles (Hebrew):**
```
1. [mako_sport] מכבי תל אביב ניצחה 87:72 ומובילה את הטבלה
2. [ynet] מכבי על הפסגה: ניצחון דרמטי
```

**fb_caption:**
```
Маккаби Тель-Авив разгромила соперника 87:72 и вышла в лидеры

В пятничном матче баскетбольной лиги Маккаби Тель-Авив одержала уверенную победу.
Счёт встречи — 87:72 — позволил клубу выйти на первое место турнирной таблицы.
Игра проходила при полных трибунах фанатов в спортзале «Менора Миват».

Болеете ли вы за Маккаби?

Подробнее → https://www.mako.co.il/sport/article/xyz789
```

---

## DB Storage

The WOW caption is stored in **`stories.fb_caption`** (separate from `summary_ru`).

- `summary_ru` — 5-section format, used by the web site and CF sync
- `fb_caption` — WOW-story format, used exclusively for Facebook posts
- `hashtags` — still generated for CF sync compatibility; not included in FB post

The publish queue (`publish/queue.py :: _format_message`) uses `fb_caption`
when available, and falls back to the legacy `title_ru + summary_ru + hashtags`
format for older stories that were published before this feature was deployed.

---

## Metrics

| Phase | Key | Description |
|-------|-----|-------------|
| `wow_story` | `caption_ok` | Captions that passed all guards |
| `wow_story` | `caption_fail` | Failed generations (fact extract fail + guard exhaustion) |
| `wow_story` | `rewrite_attempts` | Total critic rewrite attempts across all stories |

View in daily report or query directly:
```sql
SELECT key, SUM(value) FROM metrics WHERE phase = 'wow_story' GROUP BY key;
```

---

## Safety Notes

- No ragebait, no calls for violence, no personal accusations.
- Speculation phrases (`ожидается`, `собираются`, `планируют`, `намерены`)
  are **banned** by `guard_wow_hallucination` unless explicitly present in
  `ExtractedFacts.claims`.
- High-risk stories (`risk_level=high`) are required by
  `guard_wow_high_risk_attribution` to include an attribution phrase.
- All numbers from source titles must appear in the post
  (`guard_wow_numbers`).
