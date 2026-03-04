## Codex Skills

Canonical skills for this repository live only in:

- `/.agents/skills/*/SKILL.md`

Why this layout:

- avoids duplicate skill loading across `.agents`, local `.codex`, and global `%USERPROFILE%\.codex`
- keeps one source of truth for edits and reviews

Current policy:

- do not mirror `.agents/skills` into this folder
- do not create project-specific global copies under `%USERPROFILE%\.codex\skills`