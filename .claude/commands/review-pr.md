---
description: Review a teammate's PR (usage: /review-pr 12)
argument-hint: <PR number>
---
`gh pr view $ARGUMENTS` and `gh pr diff $ARGUMENTS`. Check: files are inside the author's role (TEAM.md §1), no data/
secrets, CLAUDE.md non-negotiables respected (no hardcoded case answers, no stack change, routes from actions.py),
checks in the description. Check out the branch and run pytest (+ the check loop if agent/ or cases/ changed).
Post the review with `gh pr review` (approve or request changes with concrete line references).
