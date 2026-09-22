# TEAM.md — How the 3 of us build Fraud Detection Agent together

**Deadline:** Thu 24 Sep 2026 (confirm the hour on Discord).
**Tools:** GitHub (one repo) + Claude Code (each member) + Claude chat (the prompt writer and reviewer).
**Rule:** one task = one branch = one owner = one pull request. Nobody edits files owned by someone else without saying so in the team chat.

---

## 1. Roles (decide names in the first 10 minutes)

| Role | Member | Owns (files) | Roadmap steps |
|---|---|---|---|
| **A — Graph & Data** | _name_ | `scripts/01–05`, `graph/*.gsql`, `agent/tg_conn.py`, `.mcp.json`, `scripts/monitor.py` | 2, 3, 5, 6, 7, 8, 16 |
| **B — Agent & Policy** | _name_ | `agent/detectors.py`, `agent/policy.py`, `agent/actions.py`, `agent/investigator.py`, `agent/retrieval.py`, `agent/narrative.py`, `agent/backends.py`, `run_cases.py`, `scripts/backtest.py`, `scripts/demo_uncertainty.py`, `tests/`, `cases/`, `ui/traces/` | 9, 10, 11, 12, 13, 14, 15 |
| **C — Delivery & Format** (team lead) | _name_ | `README.md`, `ROADMAP.md`, `TEAM.md`, `TASKS.md`, `docs/`, `ui/build_case_view.py`, `ui/case_view.html`, `scripts/validate_answers.py`, `.github/`, the video | 0, 1, 4, 17, 18, 19, 20, 21 + GitHub admin + answer-format owner |

**Shared files** (anyone can edit, but announce it in the team chat first):
- `CLAUDE.md`
- `requirements.txt`
- `rag/`

**Cross-role rules:**
- `backends.py` belongs to B. If A adds a GSQL query, A tells B the query name and the shape of its output. B then adds the method in `backends.py`.
- Only **B** runs `run_cases.py` and commits `cases/` and `ui/traces/`. This avoids three different versions of the answer files.
- Only **A** changes the TigerGraph schema or reloads data on Savanna. Everyone else only reads the graph.

---

## 2. Git workflow (Claude Code follows this automatically — see CLAUDE.md)

```
main                      ← always working; protected; changes only through PRs
 └─ feat/A-step6-load     ← one branch per task: feat/<role>-step<N>-<short-name>
 └─ feat/B-step10-tune
 └─ fix/B-ring-threshold  ← fixes: fix/<role>-<short-name>
```

**Starting a task** (`/start-task`):
1. `git checkout main && git pull`
2. `git checkout -b feat/<role>-step<N>-<name>`
3. Mark the task **IN PROGRESS** in `TASKS.md`.

**While working:**
- Commit small and often, using the message format `[A] step6: chunked loading job for txns`.
- Push the branch at least every hour, so the others can see progress.

**Finishing a task** (`/finish-task`):
1. Run the check loop.
2. Update `TASKS.md` and `docs/SESSION_LOG.md`.
3. `git pull --rebase origin main`, then push the branch.
4. Open a pull request.
5. Another member approves it. Squash-merge.

**Never:**
- force-push to `main`
- commit `.env`, `data/`, or the CSVs
- edit another role's files without asking
- merge when the CI check is red

---

## 3. Time plan (with time boxes)

Each day has two 10-minute stand-ups: **10:00** and **18:00**. Each person answers three questions: what I finished, what I'm doing next, and what is blocking me.
Merges happen in **merge windows**: **13:00** and **20:00**. C merges the approved pull requests and everyone runs `git pull`.

### Day 0 — Mon 21 Sep
| Time | A — Graph & Data | B — Agent & Policy | C — Delivery |
|---|---|---|---|
| First hour | Clone, set up venv | Clone, set up venv | **Push the base repo**, protect `main`, turn on CI, add teammates |
| Next 2 h | Step 2 feature store | Step 1: read the policy, dry-run the local benchmark | Step 1: answer-format audit of `cases/` |
| Next 2 h | Step 3 model | Review detectors vs the dataset README | Step 4: create the **Savanna** workspace, share credentials privately |
| Evening | Share `data/*.pkl` via Drive (not Git) | Local run shows 20/20 valid | TASKS.md up to date; plan for Day 1 |

### Day 1 — Tue 22 Sep
| Time | A | B | C |
|---|---|---|---|
| Morning | Steps 5–6: schema + load | Step 9: detector review | Blog skeleton + architecture diagram |
| Afternoon | Steps 7–8: graph check, install queries, MCP | Step 10: backtest + tuning | Case view polish, demo storyboard |
| Evening | Hand the query list to B | Merge tuning after benchmark check | Merge window; TASKS.md |

### Day 2 — Wed 23 Sep
| Time | A | B | C |
|---|---|---|---|
| Morning | Support: fix query errors, check MCP tool calls | Steps 11–13: policy, permissions, GraphRAG check | Screenshots from GraphStudio |
| Afternoon | Check the 20 InvestigationCase vertices in the graph | Step 14 uncertainty proof, **Step 15: run the 20 cases into the graph** | Step 17 case view rebuild; record draft video segments |
| Evening | Step 16 monitor (optional) | Freeze `cases/` (**code freeze 22:00**) | Blog draft complete |

### Day 3 — Thu 24 Sep (no new features)
| Time | Everyone |
|---|---|
| Morning | C: Step 18 format review. A + B: fix only what the review finds. |
| Midday | C: record the video. A: GraphStudio segment. B: uncertainty-proof segment. |
| Afternoon | Blog + social post published, repo made public, **submit 3+ hours before the deadline** |

---

## 4. Working with Claude chat (the prompt writer)

After each Claude Code session, paste this **session report** into Claude chat:

```
SESSION REPORT
Member/role: A | B | C
Roadmap step: <N>
Branch: <branch name>
What I did: <2-4 lines>
Result / error: <paste the last output, or the error text>
Repo: <GitHub URL> (commit <hash> if pushed)
Next I want to: <task>
Time available: <e.g. 90 min>
```

Claude chat reads the repo and replies with:
1. A short review: what's fine, what's risky, and any conflict with the other members' work.
2. **One ready-to-paste Claude Code prompt** that:
   - names the branch and the files allowed to change
   - gives exact "done when" checks
   - includes the commit and push steps
   - includes a time box
3. What to tell the other two members, if anything affects them.

---

## 5. Definition of done (every pull request)
- [ ] Only the files the task owns were changed (`git diff --stat` in the PR description)
- [ ] The check loop passes: `validate_answers.py` → 0 errors, `pytest` → all passed (for B's changes)
- [ ] The verdict table in the PR description is unchanged, or the changes are explained
- [ ] `TASKS.md` status updated, `docs/SESSION_LOG.md` entry added
- [ ] CI is green
