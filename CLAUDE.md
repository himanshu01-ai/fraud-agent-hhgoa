# Fraud Detection Agent — instructions for Claude Code

Hackathon project: **TigerGraph × Hacker House Goa 2026 — Agentic Fraud Investigation (IEEE-CIS edition)**.
Deadline **Thu 24 Sep 2026**. The build plan is `ROADMAP.md` (Steps 0–21). The user runs it step by step with `/step N`.

## About the user
IT administrator; prefers concise, direct answers; complete ready-to-run code after each change (no partial
snippets); grounded in real data numbers. Reply in the language of the prompt (English → English; otherwise Hinglish).

## Non-negotiables
1. **Never change the stack**: Python 3.11, pandas/numpy, LightGBM + scikit-learn, TigerGraph Savanna, GSQL,
   pyTigerGraph, TigerGraph MCP (`tigergraph-mcp`), GraphRAG (graph + TF-IDF + policy text), optional Anthropic LLM,
   offline HTML case view (`ui/case_view.html`, no CDN). No LangGraph, no Streamlit, no new services.
2. **Never change agent functionality**: trigger → investigate (as of `opened_at`, no look-ahead) → detectors →
   assess → evidence request (capped, simulated reply recorded) → initial/final actions (R1–R10) → §3a case vs SAR →
   §6 stop → explain → write InvestigationCase to TigerGraph.
3. **Always use the given dataset** (`$DATA` folder). Never use the public Kaggle/IEEE-CIS files (disqualification).
   Every ID written to an answer file must exist in the dataset.
4. **The LLM never decides.** Verdicts/actions come from `agent/policy.py`; routes only from `agent/actions.py`
   (`required_route`). Permission checks live in code (`ActionExecutor`), never in prompts.
5. **No hardcoding benchmark answers.** Change detector weights/thresholds, never `if case_id == ...`.
6. Answer format = dataset README "Answer Format" section. After ANY change to agent/ run the check loop below.

## Check loop (run after every change to agent/)
```bash
rm -f data/case_memory.json
python run_cases.py --data-dir $DATA --backend local        # or tigergraph / mcp
python scripts/validate_answers.py $DATA                    # must print: files with errors: 0
python -m pytest -q tests                                    # must all pass
python ui/build_case_view.py
```
Report the verdict table (case, verdict, p, pattern, exposure, sar) and what changed vs the previous run.

## Data facts (verified)
- transactions: 590,742 in 3 parts; **only part-001 has a header**. identity 144,432. closed cases 5,565
  (4,665 confirmed / 900 cleared). 20 benchmark cases. 13,553 customers, 14,317 cards, 9,706 device profiles.
- `card_id` = customer_id + "-K" + rank of card6 within customer (missing first, then A→Z) — 100% match.
- cardholder `uid` = customer_id + addr1 + (day − D1); customer_id alone is an aggregate (up to 14,932 txns).
- device_profile = DeviceInfo | id_30 | id_31 | id_33. Generic profiles start with "NA | NA".
- Risk score fraud-vs-cleared AUC 0.05; case-memory model 0.88. Every customer dispute in history was confirmed fraud.
- Undocumented patterns in history: sub-$500 structuring (CC-3748, 3841, 3907, 4086, 4124); SM-G935F proxy ring
  (CC-2649, 2971, 2985, 3035).

## Layout
- `scripts/01..05` pipeline + graph check; `scripts/backtest.py`, `demo_uncertainty.py`, `monitor.py`, `validate_answers.py`
- `graph/*.gsql` schema, loading jobs, 10 queries (graph `FraudGraph`)
- `agent/` backends (local / tigergraph / mcp), detectors, policy, actions, retrieval, narrative, investigator
- `cases/` 20 answer files · `ui/traces/` per-case trace · `extra_cases/` optional monitor output
- Secrets only in `.env` (never commit). Data files never committed (`.gitignore`).

## Savanna notes
Workspace must be awake (auto-start on). If a loading upload times out use `03_export_graph_csv.py --chunk 50000`.
If MCP tool discovery fails, fall back to `--backend tigergraph` and report the MCP tool list.

## Team workflow
**No fixed roles.** Anyone may take any task, but claim its row in TASKS.md (name + branch, committed and pushed)
before starting. `cases/` + `ui/traces/` and the TigerGraph schema/load are single-owner at any moment.
 (3 members — see TEAM.md, TASKS.md)
Roles: **A** Graph & Data · **B** Agent & Policy · **C** Delivery & Format. File ownership is in TEAM.md §1 and
`.github/CODEOWNERS`. At the start of every session ask "Which role are you (A/B/C) and which task?" if not given.

Every session, in this order:
1. `git status` — if there are uncommitted changes that are not yours, STOP and ask.
2. `git checkout main && git pull` then create/switch to `feat/<role>-step<N>-<name>` (or `fix/<role>-<name>`).
3. Read TASKS.md + the last 3 entries of docs/SESSION_LOG.md + `git log --oneline -10` to know what others changed.
4. **Only edit files belonging to the task you claimed in TASKS.md** (or files the prompt explicitly allows). If another role's file must change,
   stop and write the needed change as a note for that owner instead.
5. Work in small commits: `[<role>] step<N>: <what>`. Push the branch at least hourly.
6. Before finishing: run the check loop (B: always; A/C: pytest + compileall at minimum), then
   `git pull --rebase origin main`, resolve conflicts only inside owned files, push, and open a PR with
   `gh pr create --fill --base main` using the PR template (verdict table if cases/ changed).
7. Update TASKS.md (status) and prepend an entry to docs/SESSION_LOG.md, then commit + push those too.
8. End with a SESSION REPORT block (format in TEAM.md §4) the user can paste into Claude chat.

Never: push to main, force-push, rewrite others' history, commit `.env` / `data/` / CSVs, regenerate `cases/`
unless role B, change TigerGraph schema unless role A, or delete another member's code.
Time-box every task (TASKS.md column). At 80% of the time box, stop adding scope: commit what works and report.
