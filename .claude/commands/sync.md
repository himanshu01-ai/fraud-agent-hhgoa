---
description: Pull latest main into the current branch and report what teammates changed
---
`git fetch origin`, show `git log --oneline HEAD..origin/main`, summarise per role what changed and whether it
touches files this branch uses; then `git rebase origin/main` (stop and explain on conflicts outside owned files).
Rerun `python -m pytest -q tests`.
