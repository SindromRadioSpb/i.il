# docs/GLOSSARY.md — Glossary & Transliteration Rules (HE→RU)

Goal: consistent Russian rendering of Hebrew names, places, institutions, and recurring terms.

## 1) Principles
- Consistency beats perfection. Pick one variant and stick to it.
- Do not “invent” translations of official names; prefer established Russian usage when known.
- If unsure, use transliteration and keep it stable.

## 2) Transliteration baseline (simplified, practical)
This is a pragmatic baseline for news summaries (not academic transliteration).

- א (aleph) / ע (ayin): usually omitted or represented by vowel as heard
- ח: “х”
- כ/ך: “к” or “х” depending on pronunciation (prefer established forms)
- צ: “ц”
- שׁ: “ш”
- שׂ: “с”
- ת: “т”
- ר: “р”
- ו: “в” or vowel “о/у” depending on context
- י: “й” or vowel “и”

## 3) Stable institution names (examples)
Maintain a table of fixed renderings as you grow the project.
Add new entries when they appear in sources.

Example entries (extend as needed):
- “צה״ל” → “ЦАХАЛ”
- “שב״כ” → “ШАБАК”
- “משטרה” → “полиция”
- “משרד הבריאות” → “Министерство здравоохранения”
- “כנסת” → “Кнессет”

## 4) Cities and places
Prefer established Russian names:
- תל אביב → Тель-Авив
- ירושלים → Иерусалим
- חיפה → Хайфа

Add a small “top cities” list early; expand gradually.

## 5) Rule: glossary is source of truth
If a term exists in this glossary, agents must use it.
If a new recurrent term appears:
- add it here
- add a regression test to ensure it stays consistent (later implementation)

## 6) Implementation note
In code, the glossary should be loaded as structured data (YAML/JSON) and applied during summary generation.
This markdown file is the human-readable reference; the machine-readable glossary may live in `sources/glossary.yaml` (future).
