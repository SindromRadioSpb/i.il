# docs/BRAND.md — Brand, Voice & Editorial Standards

This document defines the public positioning, editorial tone, and content policies for News Hub.
It is binding for all published content and any generated copy (summaries, UI labels, social posts).

---

## 1) Brand Promise & Mission

**News Hub** is a Russian-language news digest aggregating professional Hebrew-language news sources from Israel.

**Mission statement:**
Deliver accurate, neutral, and attributed Russian summaries of Israeli news events — automatically, within minutes, and without republishing copyrighted content.

**What we are:**
- A fast, automated digest of Israeli news in Russian
- A canonical hub: every story has a permanent URL with full context
- An attribution-first publication: every summary links to its sources

**What we are not:**
- An original reporting outlet
- A platform for commentary, opinion, or analysis
- A replacement for primary sources

---

## 2) Voice & Tone

### 2.1 Core principles

| Principle | Description |
|-----------|-------------|
| **Neutral** | Report facts; do not editorialize. If something is contested, say so explicitly. |
| **Factual** | Preserve numbers, dates, names, and percentages exactly. Do not round or approximate without noting it. |
| **Clear** | Write for a Russian-speaking general audience. Avoid technical jargon unless unavoidable and then define it. |
| **Attributed** | Every claim points to a source. Unverified information is labeled as such. |
| **Concise** | Summaries are 400–700 characters. Every sentence earns its place. |

### 2.2 Do / Don't

**Do:**
- Use "по данным источников …" or "как сообщает …" to attribute
- Name sources by publication name (e.g., "Haaretz", "Ynet")
- Translate numbers, dates, and proper nouns consistently (see `docs/GLOSSARY.md`)
- Use "данные уточняются" when a situation is developing
- Mark high-risk topics (casualties, medical, security) with extra factual care

**Don't:**
- Add adjectives that express sentiment ("ужасный", "потрясающий", "шокирующий")
- Present one source's claim as established fact if other sources contradict
- Omit source links to save space
- Paraphrase in a way that changes the meaning or drops key numbers
- Use exclamation marks or capitalized words for emphasis in summaries

### 2.3 High-risk topics (risk_level = high)

For stories tagged `risk_level=high` (casualties, terror, emergencies, medical):
- **Must** use neutral phrasing only
- **Must** include "по данным источников" or equivalent
- **Must** cite ≥ 2 sources where available
- **Must not** use sensational or emotional language

---

## 3) Disclaimers

The following disclaimers apply to all published content and must be reflected in UI, FAQs, and any external communication.

### 3.1 Summary-only
> Материалы на этом сайте представляют собой **оригинальные русские изложения** новостей на основе открытых ивритоязычных источников. Мы **не воспроизводим** полные тексты статей. Ссылки на источники приведены на каждой странице.

### 3.2 Attribution
> Все материалы основаны на публично доступных новостных источниках. Мы указываем источник и ссылку для каждой публикации. News Hub не является правообладателем исходных материалов.

### 3.3 Not a primary source
> News Hub является агрегатором и **не ведёт собственную репортёрскую деятельность**. Для проверки информации обращайтесь к первоисточникам.

### 3.4 No legal or medical advice
> Ни один материал на этом сайте не является юридической, медицинской или финансовой консультацией. При необходимости обращайтесь к квалифицированным специалистам.

### 3.5 Developing stories
> Ситуации, отмеченные как "данные уточняются", могут содержать предварительную информацию, которая впоследствии изменится. Мы обновляем публикации по мере поступления подтверждённых данных.

### 3.6 Accuracy limitation
> Несмотря на все усилия по обеспечению точности, автоматизированная обработка может содержать ошибки. При обнаружении неточности, пожалуйста, сообщите нам (см. раздел «Исправления» ниже).

---

## 4) Attribution Policy

Every published story **must** include:

1. **Source names** — the publication name (e.g., "Haaretz", "Ynet", "Maariv") for each source used
2. **Source links** — a clickable link to the original article or source page
3. **Source count** — the number of sources ("2–5 источников")
4. **Attribution phrase** — at minimum one of:
   - "по данным источников …"
   - "как сообщает {source_name} …"
   - "согласно данным {source_name} и {source_name2} …"

**Rules:**
- Minimum 1 source per story at publication time; target 2–5
- If only a title/snippet was accessible (paywall, low confidence), state this explicitly
- Source names in the `sources/registry.yaml` are the canonical display names
- Do not attribute to a source unless that source's URL is in the story's items list

**What attribution does NOT mean:**
- Reproducing the source's text verbatim
- Claiming any rights over the original material
- Implying the source endorses our summary

---

## 5) Corrections Policy

Errors happen. Our corrections policy is transparent and prompt.

### 5.1 When to issue a correction
- A factual error in the published summary (wrong number, wrong name, wrong date)
- A misattribution (wrong source cited or wrong claim attributed)
- A materially misleading implication that cannot be resolved by re-reading

### 5.2 How corrections are made
1. **Update the summary** — fix the factual error in the story text
2. **Add a correction note** — append "Обновлено: {дата}: {краткое описание исправления}" at the end of the story (optional but recommended for significant errors)
3. **Do not hide corrections** — the story page shows its `last_update_at` timestamp; we do not silently overwrite without any trace
4. **Record major corrections** — if a correction significantly changes the story's meaning, record a note in `docs/DECISIONS.md` or the run log

### 5.3 Takedown requests
- If a source requests removal or a correction, disable/update promptly
- Record the decision in `docs/DECISIONS.md`
- See `docs/COMPLIANCE.md §7` for full policy

### 5.4 Contact
Corrections and takedown requests should be directed to the repository owner.
See `CONTRIBUTING.md` or the GitHub repository contact for the process.

---

## 6) Social Media (Facebook Page) Standards

When a story is crossposted to the Facebook Page:

- Post text must be short, factual, and neutral (1 headline + 2–4 bullet points)
- Must include a link to the canonical story URL on the hub
- Must not contain sensational language (see §2.2 Don't)
- Must include 1–3 relevant hashtags from the story category
- No additional claims beyond what is in the published summary

Facebook crossposting is governed by `docs/COMPLIANCE.md §5` (official API only, no scraping).

---

## 7) Consistency References

| Topic | Reference |
|-------|-----------|
| Transliteration glossary | `docs/GLOSSARY.md` |
| Summary format and sections | `docs/EDITORIAL_STYLE.md` |
| Risk levels and sensitive topics | `docs/COMPLIANCE.md §2` |
| Facebook posting rules | `docs/COMPLIANCE.md §5` |
| Data retention and privacy | `docs/COMPLIANCE.md §3` |
