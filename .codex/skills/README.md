## Codex Skills Mirror

This directory is a Codex-compatible mirror of repository skills from:

- `/.agents/skills/*/SKILL.md`

Source of truth stays in `.agents/skills`.
If source skills change, re-sync with:

```powershell
Copy-Item -Path .agents/skills/* -Destination .codex/skills -Recurse -Force
```

Global copies for this project were also created in:

- `C:\Users\Win10_Game_OS\.codex\skills\iil-*`

They are intended for Codex skill discovery in new sessions.