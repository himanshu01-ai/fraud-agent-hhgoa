# GIT_WORKFLOW.md — working in VS Code, three people, one repo

Repo: **fraud-agent-hhgoa** · Branch model: one task = one branch = one pull request · `main` is always working code.

---

## 0. The idea in one paragraph

GitHub holds the master copy. Each of you keeps a **clone** — a normal folder on your laptop. You open that folder in
VS Code and in Claude Code. Both edit the same files on your disk. Nothing reaches GitHub until you `commit` (save a
checkpoint) and `push` (upload). Because everyone pushes their own **branch** and merges through a **pull request**,
nobody can overwrite anyone's work: Git merges by line, and when two people change the same line it stops and asks.
The way to keep that pain near zero is file ownership (TEAM.md §1) — each role edits its own files.

---

## 1. One-time setup — the repo owner (member C)

Install first: Git, VS Code, Python 3.11, GitHub CLI (`gh`), Claude Code.

```bash
cd ~/projects/fraud-agent-hhgoa            # the unzipped project folder
git init
git add .
git commit -m "[C] step0: base repo (agent, gsql, scripts, docs, 20 answer files)"
gh auth login                       # log in once
gh repo create fraud-agent-hhgoa --public --source . --remote origin --push
```

Protect `main` so nobody can push straight into it:

```bash
gh api -X PUT repos/:owner/fraud-agent-hhgoa/branches/main/protection \
  -H "Accept: application/vnd.github+json" \
  -f "required_pull_request_reviews[required_approving_review_count]=1" \
  -F "enforce_admins=false" -F "restrictions=null" \
  -f "required_status_checks[strict]=true" -f "required_status_checks[contexts][]=checks"
```

If that call fails, do it by hand: **GitHub → Settings → Branches → Add rule → `main` →** tick *Require a pull request
before merging* (1 approval) and *Require status checks to pass* (`checks`).

Then add the other two: **Settings → Collaborators → Add people** (give them Write access).
Finally edit `.github/CODEOWNERS` and replace `@member-a` / `@member-b` / `@member-c` with the real GitHub usernames.

## 2. One-time setup — members A and B

```bash
gh auth login
git clone https://github.com/<owner>/fraud-agent-hhgoa.git
cd fraud-agent-hhgoa
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # fill in the Savanna details; never commit this
code .                                                 # open in VS Code
```

In VS Code install two extensions: **Python** and **GitHub Pull Requests**. Then open the terminal inside VS Code
(`Ctrl+\``) and run `claude` there — Claude Code now works on exactly the files you see in the editor.

**Data files stay off GitHub.** `transactions-part-*.csv`, `identity.csv`, `data/*.pkl` and `.env` are all in
`.gitignore`. Share them over Drive or a USB stick.

---

## 3. The daily loop (this is the whole workflow)

```bash
# 1 START — always begin from the latest main
git checkout main
git pull                                   # or VS Code: Source Control → ⋯ → Pull
git checkout -b feat/B-step10-tune         # feat/<role>-step<N>-<short-name>

# 2 WORK — edit in VS Code and/or Claude Code, then checkpoint often
git add -A
git commit -m "[B] step10: lower ring threshold, backtest AUC 0.40 → 0.52"
git push -u origin feat/B-step10-tune      # first push of the branch

# 3 BEFORE OPENING A PR — bring in whatever the others merged meanwhile
git pull --rebase origin main
# run your checks again after the rebase
python -m pytest -q tests
git push

# 4 PULL REQUEST
gh pr create --base main --fill            # or the VS Code GitHub panel

# 5 A TEAMMATE REVIEWS AND MERGES (squash merge), then everyone:
git checkout main && git pull
```

In VS Code you can do all of this from the **Source Control** panel: the branch name sits in the bottom-left corner,
staged changes and the commit box are in the panel, and **Sync Changes** does pull + push.

### Rules that prevent overwriting

1. Never commit on `main`. If `git status` shows `On branch main` with changes, run `git switch -c feat/...` first.
2. Edit only the files your role owns (TEAM.md §1). This is what keeps conflicts near zero.
3. Only member **B** runs `run_cases.py` and commits `cases/` and `ui/traces/`. Otherwise three people generate three
   different versions of the same 20 files and every merge conflicts.
4. Only member **A** changes the TigerGraph schema or reloads Savanna.
5. Pull before you start and rebase before you open the pull request.
6. Never `git push --force` on a shared branch and never on `main`.
7. Small commits, pushed at least every hour, so the others can see what you are touching.

### If Git reports a conflict

```bash
git status                       # lists the conflicted files
```
Open the file in VS Code. It shows *Accept Current / Accept Incoming / Accept Both*. Keep both sides unless the
change is clearly yours, then:
```bash
git add <file>
git rebase --continue
python -m pytest -q tests
git push
```
If the conflict is in a file you don't own, stop and message the owner. Do not "fix" their code.

---

## 4. Folder names: the roadmap vs this repo

The roadmap names `/graph`, `/agent`, `/rag`, `/ui`, `/cases`, `/docs`. This repo already has the same parts under
slightly different names, and `cases/` — the one name the answer format requires — is already correct. Keep the
current names (renaming breaks every import a day before the deadline) and note the mapping in the README:

| Roadmap | This repo |
|---|---|
| /graph | `graph/` (schema, loading jobs, 10 GSQL queries) + `agent/tg_conn.py` |
| /agent | `agent/` (investigator, policy, actions, detectors, backends) |
| /rag | `agent/retrieval.py` + `rag/` |
| /ui | `ui/` |
| /cases | `cases/` ✔ |
| /docs | `docs/` |

---

## 5. Microsoft Agent Framework — decide this today, in 5 minutes

The new roadmap names Microsoft Agent Framework 1.0. The brief lists an agent framework as **optional**, and our loop
is already a deterministic state machine (`agent/investigator.py`) with a capped evidence loop and code-enforced
permissions — which is what the rubric actually asks for. Two honest options:

- **Keep as is (recommended with 3 days left).** Zero risk. In the blog and video, state that the loop is a custom
  deterministic workflow, chosen so every transition is auditable.
- **Wrap it.** Add `agent-framework` as a thin layer that calls the same functions as workflow nodes
  (`investigate → assess → request_evidence → decide → explain → write_memory`) and use its MCP client for the
  TigerGraph tools. Nothing inside the nodes changes. Budget half a day, and only if the graph load and the 20 answer
  files are already done.

Whatever you choose, the deciding logic must stay in `policy.py` / `actions.py`, never in the framework or a prompt.

---

## 6. Telling me what you're working on

After each Claude Code session, paste this into the chat:

```
SESSION REPORT
Member/role: A | B | C
Phase / step: <e.g. Phase 3 — GSQL algorithms>
Branch: feat/A-step8-queries
What I did: <2-4 lines>
Result / error: <paste the real output or error>
Repo: https://github.com/<owner>/fraud-agent-hhgoa (commit <hash>)
Next I want to: <task>
Time available: <90 min>
```

You get back: a short review, **one ready-to-paste Claude Code prompt** naming the branch, the files it may touch, the
exact done-when checks and the push/PR steps, plus anything the other two need to know.
