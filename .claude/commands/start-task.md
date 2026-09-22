---
description: Start a task safely (usage: /start-task B 10 tune)
argument-hint: <role A|B|C> <step N> <short-name>
---
Arguments: $ARGUMENTS (role, step, short name).
1. `git status` (stop if foreign uncommitted changes), `git checkout main`, `git pull`.
2. Create or switch to branch `feat/<role>-step<N>-<short-name>`.
3. Summarise in 5 lines: the ROADMAP step goal, the files this role may edit (TEAM.md §1), what others changed
   recently (`git log --oneline -10`, last SESSION_LOG entries), and the time box from TASKS.md.
4. Set the TASKS.md row to IN PROGRESS with the branch name; commit `[<role>] step<N>: start` and push the branch.
