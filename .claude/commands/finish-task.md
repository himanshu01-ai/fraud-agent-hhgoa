---
description: Finish a task: checks, sync, PR, board, session report
---
1. Run the checks for this role (CLAUDE.md check loop for B; `python -m compileall -q agent scripts ui run_cases.py`
   and `python -m pytest -q tests` for everyone). Stop and report if anything fails.
2. `git diff --stat main` — confirm only this role's files changed; list any exception.
3. `git pull --rebase origin main`, fix conflicts only in owned files, rerun checks, push.
4. Update TASKS.md (IN REVIEW) and prepend a docs/SESSION_LOG.md entry; commit and push.
5. `gh pr create --base main --fill` (fill the PR template; include verdict table if cases/ changed).
6. Print the SESSION REPORT block from TEAM.md §4 with real numbers, the PR URL and the commit hash.
