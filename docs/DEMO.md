# docs/DEMO.md — 2‑Minute WOW Demo Script

Goal: demonstrate a professional, autonomous news hub (HE→RU) with minimal human intervention.

## Demo prerequisites
- Worker is running (local or deployed)
- Web is running (local or deployed)
- At least one ingestion run has produced at least 1 Story

Optional:
- Facebook posting enabled and token configured (for the final step)

---

## 0:00–0:15 — Open the hub feed
1) Open the web feed page.
2) Show that each card has:
   - RU title
   - short excerpt
   - category + risk level
   - “updated” time label

Talking points:
- “Сайт — канонический источник: все соцсети ведут сюда.”
- “Никаких дублей: одно событие = один Story.”

---

## 0:15–0:45 — Open a story page
1) Click a story.
2) Show the structured summary:
   - Что произошло
   - Почему важно
   - Что дальше
3) Scroll to sources list and timeline.

Talking points:
- “Это не копипаст — это оригинальное summary + ссылки на источники.”
- “Таймлайн показывает, какие источники обновляли событие.”

---

## 0:45–1:20 — Show ops/health
1) Open `/api/v1/health` in browser (or ops page if present).
2) Show last run:
   - status
   - counters
   - duration

Talking points:
- “Каждый Cron-run логируется и наблюдаем.”
- “Система устойчива: ошибки одного источника не валят весь run.”

---

## 1:20–1:45 — Explain idempotency & cost control
Talking points (no need to show UI):
- “Дедуп по item_key = sha256(normalized_url).”
- “Кластеризация избегает перевода дублей.”
- “Переводим короткие фрагменты, не полные статьи — бюджет минимальный.”

---

## 1:45–2:00 — Optional: Facebook crosspost
If enabled:
1) Open your Facebook Page and show a post that links back to the story.
2) Mention idempotency:
- “Один Story → максимум один FB пост; повторные run не дублируют.”

---

## What to say if asked about compliance
- “Мы не скрейпим Facebook.”
- “Мы не публикуем полный текст статей.”
- “Всегда есть атрибуция и ссылки на первоисточник.”
