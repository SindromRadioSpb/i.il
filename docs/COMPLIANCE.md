# docs/COMPLIANCE.md — Compliance, Copyright & Editorial Integrity

This document defines the compliance and editorial rules for the news hub.
If anything conflicts with this document, **this document wins**.

---

## 1) Core compliance principles

### 1.1 Summary-only publication (mandatory)
- We publish **original Russian summaries**.
- We do **not** republish full copyrighted articles verbatim.
- We do **not** reproduce substantial portions of text from sources.

Allowed:
- Title paraphrase (not exact copy unless extremely short/common)
- Short quoted fragments only when necessary and minimal (prefer none)
- Links to original sources with clear attribution

### 1.2 Attribution is mandatory
Each published story must include:
- Source names and links (2–5 when available)
- Clear language: “по данным источников …” when appropriate

### 1.3 No Facebook scraping
- We do not scrape Facebook UI.
- We do not use browser automation to read other pages/groups.
- Facebook is used only as:
  - a distribution channel (posting to our own Page via official API)
  - an engagement metric source (if permitted by API)

---

## 2) Content rules (editorial integrity)

### 2.1 Accuracy & neutrality
- Avoid speculation. If not confirmed, explicitly label as such.
- Use neutral tone, especially for sensitive topics.
- Preserve factual numbers (casualties, sums, percentages) accurately.

### 2.2 Sensitive topics (risk-bucket)
Stories are labeled `risk_level`:
- `low`: routine news
- `medium`: politics/courts
- `high`: casualties, terror attacks, emergencies, health crises

For `high`:
- Must use neutral phrasing.
- Must prefer ≥2 sources when available.
- Must avoid sensational wording (“шок”, “ужас”, “кошмар”, etc.).
- Must include “по данным источников” or equivalent.

### 2.3 Avoid misinformation amplification
- If sources contradict each other, summarize carefully:
  - “разные источники сообщают …”
  - “данные уточняются”
- Do not present unverified claims as fact.

---

## 3) Data handling & privacy

### 3.1 No user PII
- Do not collect or store personal information about readers.
- No profiling, no individualized tracking by default.

### 3.2 Minimal retention
- Store only what is needed:
  - source URL, normalized URL
  - title
  - short snippet for processing (truncated)
  - RU summary
  - timestamps and state
- Avoid storing full article bodies.

---

## 4) Source usage policy

### 4.1 Allowed sources
Sources must be:
- public and accessible without bypassing paywalls
- listed in `sources/registry.yaml`
- fetched with respectful throttling

### 4.2 Paywalled or restricted content
If an article is behind a paywall or content is unavailable:
- Do not attempt to bypass.
- Store minimal metadata (title + link).
- Mark `content_confidence=low`.
- Summary must be based only on accessible text (title/snippet).

### 4.3 Respect robots and terms (practical)
- Use reasonable request rates.
- Identify ourselves via a simple User-Agent (if applicable).
- If a source requests removal, disable it and record a decision in `docs/DECISIONS.md`.

---

## 5) Facebook crossposting policy

### 5.1 Official API only
Crossposting uses official Facebook Graph API for Pages.
- Store `fb_post_id` and status for idempotency.
- Do not attempt to read or harvest content from other pages.

### 5.2 Post composition
Facebook posts must:
- be short and readable
- link to the canonical hub story URL
- include minimal hashtags (1–3)

---

## 6) Translation & transformation rules

### 6.1 Translate summaries, not articles
To control cost and reduce copyright risk:
- Translate only summary-sized inputs by default.
- Use clustering to avoid translating duplicates.

### 6.2 Consistency rules
- Maintain glossary for names, places, institutions.
- Numbers must be preserved.
- Dates must be localized and consistent.

---

## 7) Takedown / corrections policy

### 7.1 Corrections
If an error is found:
- Update the story summary promptly.
- Add a short “Обновлено: …” note (optional).
- Do not hide corrections unless legally required.

### 7.2 Source takedown requests
If a source requests removal:
- Remove/disable the source entry where appropriate.
- Keep internal run logs minimal and non-sensitive.
- Record the decision in `docs/DECISIONS.md`.

---

## 8) Compliance acceptance checklist

A PR is compliance-acceptable if:
- It does not introduce copying of full source text into public pages.
- It preserves attribution rules (sources list + links).
- It does not introduce Facebook scraping.
- It maintains neutral, non-sensational style for `risk_level=high`.
- It does not expand data retention beyond what is required.
- It updates docs if any compliance behavior changes.
