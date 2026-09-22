# Fraud Detection Agent — Combined Build Roadmap (Mon 21 → Thu 24 Sep 2026)

This roadmap merges **our 4-day roadmap** with **the 10-phase roadmap from your friend**. It keeps our fixed stack and data, adds the friend's strongest ideas, and orders everything by how the project is judged.

**Deadline:** Thursday 24 Sep 2026. Confirm the exact hour on the TigerGraph Discord today.

**How to use it with Claude Code:** open the repo folder and run `claude`. `CLAUDE.md` loads automatically. For each step, type `/step N`. Claude Code will explain the step, run it, and check the **Done when** line before you move on.

---

## 1. What changed after merging the two roadmaps

| Idea from the friend's roadmap | What we did | Where |
|---|---|---|
| Validate the graph load, never trust a silent load | Added a graph check script that compares counts and spot-checks known cases | `scripts/05_check_graph.py` |
| Real graph algorithm + proximity to known fraud | Added two GSQL queries: `fraud_proximity` (2-hop path to confirmed-fraud cases) and `ring_scan` (finds rare devices hitting many cards) | `graph/queries.gsql` |
| Test the queries against closed cases before adding the LLM | Added a backtest that replays October closed cases with graph evidence only | `scripts/backtest.py` |
| Prove the recommendation changes when evidence arrives | Added a demo that runs one case with the reply set to confirm, deny and no reply | `scripts/demo_uncertainty.py` |
| Cap the evidence loop at 2–3 rounds | Hard cap in code | `MAX_EVIDENCE_ROUNDS` in `agent/policy.py` |
| Permissions enforced in code, not in the prompt | One permission table, an action executor, mock action APIs, and adversarial tests | `agent/actions.py`, `tests/test_permissions.py` |
| Keep a full decision history in the case object | Assessment → evidence request → reassessment → execution log. Saved in the trace and in the graph | `agent/investigator.py` |
| Memory must live in the graph | InvestigationCase vertex + INV_* edges, read back by later cases | `agent/backends.py`, `case_memory` query |
| Re-read the README answer format before submitting | Validator script + answer-contract tests | `scripts/validate_answers.py`, `tests/test_answers.py` |
| Simple UI that a judge understands in 60 seconds | New one-case "case file" view. The old dashboard is removed | `ui/build_case_view.py` |
| Optional: investigate beyond the 20 cases (counts for Innovation) | Weekly ring monitor → `extra_cases/` | `scripts/monitor.py` |
| Team roles | Four roles (see section 3) | — |

### Friend's suggestions we did not adopt, and why

| Suggestion | Decision |
|---|---|
| LangGraph for the agent loop | **Not used.** The brief allows a custom agent, so the loop stays a plain Python state machine in `investigator.py` with a hard cap. There is no new dependency, and every transition is deterministic and auditable. |
| Streamlit dashboard | **Not used.** You prefer a standalone offline HTML page. It needs no server, so it can't break during the demo. |
| Merchant, Account and IP nodes | **Not in the dataset.** There are no merchant or IP fields. Device profile, email domain, billing region and cardholder profile play that role. |
| Vector embeddings first | **TF-IDF first.** It needs no extra service and cites real closed cases. TigerVector is listed as a stretch goal only. |
| 20-day schedule | **Compressed to 4 days**, because the deadline is Thursday 24 Sep. |

---

## 2. The fixed stack and agent functions (never change)

**Stack:**
- Python 3.11
- pandas / numpy
- LightGBM + scikit-learn
- TigerGraph Savanna
- GSQL
- pyTigerGraph
- TigerGraph MCP
- GraphRAG (graph results + TF-IDF over closed-case notes + policy text)
- Anthropic Claude (optional; writes explanations only)
- Offline HTML case view
- GitHub

**Agent flow (brief steps 1–8):**

1. **Trigger:** accept a risk-score alert, a customer report or an analyst request.
2. **Investigate:** gather graph evidence as of the case opening time (no future data).
3. **Detect:** structuring, card testing, device ring, repeated charges, new device/email/product, unusual amount, region vs trip, cardholder habit, proximity to known fraud, case-memory model.
4. **Assess:** compute the fraud probability and count independent pieces of evidence.
5. **Gather more evidence:** verify with the customer or require step-up authentication (R1). The reply is simulated and written down. The loop is capped.
6. **Next best actions:** initial and final actions under R1–R10, with approval routes (auto / L1 / L2) enforced in code.
7. **Case vs report:** apply the §3a rule to decide case only or case + SAR.
8. **Stop and explain:** apply the §6 stopping rules, cite a rule for every action, write the summary and the SAR narrative.
9. **Case memory:** write the case into TigerGraph so later cases can retrieve it.

---

## 3. Priorities (from the judging weights)

| Weight | Criterion | What protects it |
|---|---|---|
| 25% | Investigation accuracy | Clean data (Step 2), graph queries (Step 7), detectors (Step 9), backtest (Step 10) |
| 25% | Next best action | Policy engine, before/after recommendation, SAR vs case-only decision (Steps 11, 15) |
| 15% | Agentic design | MCP tools, loop cap, code permissions, memory in the graph (Steps 8, 12, 14, 16) |
| 15% | Innovation | Case-memory model, cardholder profile, ring detection, undocumented patterns, monitor |
| 10% | Explainability | Evidence with IDs, rule citations, decision history, stand-alone SAR (Step 13) |
| 10% | Demo | Case view + a video that opens with the changing recommendation (Steps 17, 20) |

**If time runs short, protect these in order:**
1. Graph queries and detectors
2. The uncertainty loop with a visible change
3. Code-enforced permissions
4. 20 valid answer files written to the graph
5. Video
6. Blog
7. UI polish

### Team roles (if you are more than one person)

| Role | Owns |
|---|---|
| Graph owner | Steps 5–7, 10 |
| Agent owner | Steps 8–9, 11–14 |
| UI and demo owner | Steps 17, 20 |
| Answer-format owner | Steps 15, 18 — re-reads the README answer format the day before submission and compares our files against it |

If you are solo, keep this order.

---

## 4. Dataset facts we build on

| Item | Value |
|---|---|
| Transactions | 590,742 in 3 parts. **Only part-001 has a header.** |
| Identity records | 144,432 |
| Closed cases | 5,565 (4,665 confirmed fraud, 900 cleared) |
| Benchmark cases | 20 (HHG-001 to HHG-020) |
| Customers / cards / device profiles | 13,553 / 14,317 / 9,706 |
| `card_id` rule | customer_id + "-K" + rank of card6 (missing first, then A→Z). Matches 100% of the given IDs. |
| Cardholder profile | customer_id + addr1 + (day − D1). Separates real people inside big customer IDs. |
| Customer disputes in history | 100% confirmed fraud. All 900 cleared cases came from model alerts. |
| Risk score among alerts | AUC 0.05 for fraud vs cleared. The case-memory model gets 0.88. |
| Undocumented patterns in history | Purchases just under $500 (5 cases); SM-G935F device ring behind a proxy (4 cases) |

---

## 5. The plan, day by day

### DAY 0 — Monday 21 Sep · Foundation and data

**Brief:** we set up the repo and turn the raw CSVs into a feature store we can trust. We use pandas for data preparation and LightGBM to learn from the bank's closed cases, and we open the TigerGraph Savanna workspace. Nothing is agentic yet: every later decision depends on today being right.

**Step 0 · Setup (30 min)**
- **Use:** Git/GitHub, Python venv, `.env`.
- **Do:**
  - Unzip the repo.
  - `python -m venv .venv`, then `pip install -r requirements.txt`.
  - `cp .env.example .env`.
  - Put the dataset folder path in the `DATA` variable.
- **Done when:** `python -m pytest -q tests/test_permissions.py` shows 7 passed.

**Step 1 · Know the data (45 min)**
- **Use:** the dataset README; `rag/fraud_policy.md` and `rag/fraud_patterns.md`.
- **Do:** read the Answer Format and Fraud Policy sections. Confirm the file counts from section 4.
- **Done when:** you can explain R1, R2, R6, R9, §3a and §6 in one sentence each.
- **FOCUS:** the answer format decides the score for all 20 cases at once.

**Step 2 · Feature store (1 h)** — `scripts/01_build_features.py`
- **Use:** pandas.
- **Functions:** join the 3 parts, join identity, build `device_profile`, derive `card_id`, build the cardholder `uid`.
- **Done when:** it prints `transactions 590742`, `cards 14317` and `device profiles 9706`.

**Step 3 · Case-memory model (1 h)** — `scripts/02_train_case_memory_model.py`
- **Use:** LightGBM and scikit-learn. Needs about 3 GB of RAM.
- **Done when:**
  - Hold-out AUC ≈ 0.91 (risk score 0.865).
  - Fraud-vs-cleared AUC ≈ 0.88 (risk score 0.05).
- **Rule:** never use the public Kaggle labels. That means disqualification.

**Step 4 · Savanna workspace (30 min)**
- **Use:** TigerGraph Savanna.
- **Do:** create the workspace, **turn on auto-stop and auto-start**, create a secret, fill `.env`.
- **Done when:** `python -c "from agent.tg_conn import connect; print(connect().getVer())"` prints a version.

**End of day:** `data/tx_core.pkl` and `data/scores.pkl` exist, and TigerGraph is reachable.

---

### DAY 1 — Tuesday 22 Sep · Graph, queries and detectors

**Brief:** we move the data into TigerGraph and give the agent its tools.
- **GSQL** defines the schema and 10 investigation queries.
- **pyTigerGraph** loads the data and installs the queries.
- **TigerGraph MCP** exposes the queries as tools.
- The **detectors** turn query results into evidence with real IDs.
- The **backtest** checks that evidence against closed cases before any LLM is involved.

**Step 5 · Schema (30 min)** — `graph/schema.gsql`
- **Vertices (9):** Customer, Card, Txn, DeviceProfile, EmailDomain, BillingRegion, Cardholder, ClosedCase, InvestigationCase.
- **Edges (14):** undirected, including INV_* for case memory.
- **Done when:** the schema is visible in GraphStudio.

**Step 6 · Export and load (1.5 h)** — `scripts/03_export_graph_csv.py`, then `scripts/04_load_tigergraph.py --steps schema,load`
- **Use:** pandas to write the CSVs in 100k chunks; a GSQL loading job; `runLoadingJobWithFile`.
- **Done when:** the load completes. If an upload times out, lower `--chunk` to 50000.

**Step 7 · Validate the load (30 min)** — `scripts/05_check_graph.py`
- **FOCUS:** a silently broken load (a wrong edge or a missing device link) ruins accuracy and is hard to debug later.
- **Done when:** it prints `GRAPH VALID`. This means all counts match and the HHG-006 episode, the SM-G935F footprint and the ring's closed cases are all found.

**Step 8 · Install the queries (45 min)** — `04_load_tigergraph.py --steps queries`

| Query | What it gives the agent |
|---|---|
| `card_txns` | Card history and activity in a time window |
| `device_txns` | Everything done from one device profile |
| `device_footprint` | Whether a device is rare (a signal) or common (noise) |
| `cardholder_txns` | The real person's habits |
| `shared_device_cards` | Two-hop card → device → card traversal |
| `fraud_proximity` | Confirmed-fraud cases within two hops |
| `ring_scan` | Rare devices hitting 3 or more cards in a window |
| `cases_by_card` | Prior closed cases on the card |
| `cases_by_device` | Prior closed cases on the device |
| `case_memory` | Our own earlier investigations |

- **Also:** `pip install tigergraph-mcp`. The MCP config is already in `.mcp.json`.
- **Done when:** `run_cases.py --backend mcp --cases HHG-014` completes and shows its tool calls.

**Step 9 · Detectors (review and tune, 1.5 h)** — `agent/detectors.py`
- **Done when:** these signals fire on these cases:
  - HHG-006 → structuring
  - HHG-014 → ring (undocumented)
  - HHG-019 → ring (undocumented)
  - HHG-008 → repeated charges
  - HHG-001 → cardholder habit

**Step 10 · Backtest the graph evidence (45 min)** — `scripts/backtest.py --n 300`
- **What it does:** replays October closed cases with the trigger set to a risk score and the model signal switched off, so we measure the graph evidence alone.
- **Today's baseline:** AUC ≈ 0.40, pattern agreement ≈ 0.34.
- **What to tune:** detector weights and thresholds. Rerun the benchmark after every change.
- **FOCUS:** this is the 25% accuracy criterion. Tune here, not in prompts.

**End of day:** graph valid, 10 queries installed, MCP tool calls working, backtest numbers recorded.

---

### DAY 2 — Wednesday 23 Sep · Decision, memory, outputs and UI

**Brief:** we build and prove the parts that decide and explain.
- A deterministic **policy engine** turns evidence into actions.
- An **action executor** enforces the permission table in code.
- **GraphRAG** retrieves memory from the graph, closed-case notes and policy text.
- **Claude** (optional) rewrites the explanations from those facts only.
- Every case is written into **TigerGraph**, and the **case view** shows each case clearly.

**Step 11 · Policy engine (1 h)** — `agent/policy.py`
- **Three paths:**
  - **Strong legitimate** (p ≤ 0.15 with 2+ pieces of evidence): close.
  - **Strong fraud** (p ≥ 0.85 with 2+, or a dispute with p ≥ 0.5): act.
  - **Uncertain:** CREATE_CASE + VERIFY (+ STEP_UP_AUTH), then the reply, then the final actions.
- **Done when:** every action cites a rule and its route comes from `agent/actions.py`.

**Step 12 · Permissions in code (45 min)** — `agent/actions.py`, `tests/test_permissions.py`
- **FOCUS:** judges will probe this.
  - The agent executes `auto` actions only.
  - L1 and L2 actions are recorded as `pending_approval`.
  - A team lead approving FILE_REPORT raises `PermissionDenied`.
  - Unknown or injected actions are rejected.
- **Done when:** `pytest tests/test_permissions.py` passes, and every case trace has a decision history with the execution statuses.

**Step 13 · GraphRAG and explanations (45 min)** — `agent/retrieval.py`, `agent/narrative.py`
- **Done when:**
  - HHG-006 retrieves CC-3748, CC-3841 and CC-4124.
  - HHG-014 retrieves CC-2649, CC-2971, CC-2985 and CC-3035.
  - With `--llm`, `tokens` is above 0 and the numbers and IDs are unchanged.

**Step 14 · The uncertainty proof (30 min)** — `scripts/demo_uncertainty.py --case HHG-002`
- **FOCUS:** this is the 25% next-best-action criterion. It shows three outcomes from one starting point:
  - confirm → CLOSE_NO_FRAUD
  - deny → BLOCK_CARD (L1) + CREATE_CASE, probability 0.18 → 0.86
  - no reply → MONITOR_CARD + DECLINE_TRANSACTION
- **Done when:** the output shows the recommendation changing. This goes into the video.

**Step 15 · Run the 20 cases into the graph (1 h)**
```
python run_cases.py --data-dir $DATA --backend mcp --llm      # or --backend tigergraph
python scripts/validate_answers.py $DATA                     # → files with errors: 0
python -m pytest -q tests                                     # → all passed
```
- **Done when:**
  - All 20 files show `"written_to_graph": true`.
  - GraphStudio shows 20 InvestigationCase vertices linked to their cards, transactions, devices and closed cases.
  - Running the cases in date order shows memory hits: HHG-004 retrieves INV-HHG-016 and INV-HHG-011, and HHG-009 retrieves INV-HHG-008.

**Step 16 · Optional monitor (30 min, Innovation)** — `scripts/monitor.py --max-cases 25` → `extra_cases/`

**Step 17 · Case view (30 min)** — `python ui/build_case_view.py`, then open `ui/case_view.html`
- **Layout:** one case at a time, in this order:
  1. Decision
  2. What we recommend (before → after)
  3. Why
  4. Report
  5. Collapsed details: steps, permissions, IDs, tool calls
- **Done when:** someone new understands a case within 60 seconds.

**End of day:** 20 valid answer files written to the graph, the uncertainty proof recorded, the case view ready.

---

### DAY 3 — Thursday 24 Sep · Ship (no new features)

**Brief:** we review, tell the story and submit, using GitHub, a screen recorder (OBS or Loom), and LinkedIn or X.

**Step 18 · Final review (1 h)**
- **FOCUS:** the answer-format owner re-reads the README Answer Format and compares it against 3 of our files.
- **Rerun:** `validate_answers.py` and `pytest`.
- **Check every case:** the verdict makes sense, the actions follow the policy, and a SAR appears only where §3a requires it.

**Step 19 · README, architecture diagram and blog (1.5 h)**
- Use `README.md` and `docs/BLOG.md`.
- **Add:**
  - your backtest numbers
  - the uncertainty-proof output
  - a GraphStudio screenshot of one InvestigationCase with its edges

**Step 20 · Demo video, 3–5 min (1.5 h)** — lead with the uncertainty loop, not a UI tour

| Time | Show |
|---|---|
| 0:00 | Hook: "The bank's score separates fraud from false alarms with AUC 0.05 — we start from the graph" |
| 0:25 | HHG-002 with the uncertainty proof: the same alert under three replies gives three recommendations |
| 1:20 | HHG-019: one odd $99.92 purchase becomes a 5-card ring (`shared_device_cards`) → R6, SAR, L1/L2 pending |
| 2:10 | HHG-006: undocumented structuring, its SAR, and the five matching closed cases |
| 2:50 | Permissions: the adversarial test output; a team lead cannot file a SAR |
| 3:20 | Memory: InvestigationCase vertices in GraphStudio; the architecture slide; close |

**Step 21 · Social post and submission (1 h, finish 3+ hours before the deadline)**
- [ ] Repo made public: the README runs from a clean clone
- [ ] 20 answer files in `cases/`, validated, written to the graph
- [ ] Optional `extra_cases/`
- [ ] Video link
- [ ] Blog link
- [ ] LinkedIn/X post tagging **@TigerGraphDB**
- [ ] Submitted

---

## 6. Risks and fallbacks (no scope change)

| Risk | Fallback |
|---|---|
| The Savanna load is slow | Smaller chunks; load closed cases first; keep the workspace awake during the load |
| MCP tool names differ | The backend finds tool names when it starts; `--backend tigergraph` (pyTigerGraph) is the fallback |
| A GSQL query fails to install | Install queries one at a time; send the error to Claude Code with `/step 8` |
| No LLM key | Template explanations are complete; `tokens` = 0 |
| Out of memory | Close other apps; lower the background sample in Step 3 to 100k |
| Time runs short | Follow the protect-order in section 3 |
