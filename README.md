# Fraud Detection Agent — Agentic Fraud Investigation on TigerGraph

**TigerGraph × Hacker House Goa 2026 · Agentic Fraud Investigation (IEEE-CIS edition)**

An agent that takes a fraud alert (model score, customer report or analyst request), investigates it through
GSQL traversals on a TigerGraph knowledge graph, weighs the evidence against the bank's own closed cases,
asks for more evidence when the signals are weak, recommends policy-routed next best actions *before and after*
that evidence arrives, files a suspicious activity report when the policy requires it, and writes every
investigation back into the graph as case memory.

> A risk score is a reason to look, never a verdict. On the bank's own October hold-out, the risk score has an
> AUC of **0.05** for separating confirmed fraud from cleared alerts — the cleared alerts are exactly the
> high-score false alarms. Fraud Detection Agent starts from the graph, not the score.

## Results on the 20 benchmark cases

| | |
|---|---|
| Verdicts | 8 fraud · 12 legitimate (the README says roughly half are legitimate) |
| Undocumented patterns found | **Threshold structuring** (HHG-006: 4 purchases just under $500 in 30 min, $1,906.07) and **shared-device rings** (HHG-014: SM-G935F ring on 20 cards, 100% New device + anonymous proxy; HHG-019: a device seen only 5 times ever, ~$100 each, same email domain, 5 cards in 6 days) |
| SARs filed | 3 (006, 014, 019) — case-only for the rest, per §3a |
| Evidence requests | Used on every weak-signal alert (R1); the recommendation changes after the simulated reply and both are recorded |
| Answer files | `cases/HHG-001.json … HHG-020.json`, validated by `scripts/validate_answers.py` (every ID exists in the dataset) |

## Architecture

```
case_pack trigger ─► Investigator (agent/investigator.py)
                        │ 1 trigger  2 open context  3 gather evidence (as of case open time, no look-ahead)
                        ▼
      Graph tools (agent/backends.py) ── TigerGraph MCP server  ─┐
                                      ── pyTigerGraph RESTPP     ├─► installed GSQL queries (graph/queries.gsql)
                                      ── local mirror (offline) ─┘   card_txns · device_txns · device_footprint ·
                        │                                             cardholder_txns · shared_device_cards (2-hop) ·
                        ▼                                             cases_by_card · cases_by_device · case_memory
      Detectors (agent/detectors.py): structuring · card testing · device ring · repeat-charge burst ·
                 new device / email / product · amount · region vs trip · cardholder habit · case-memory model
                        ▼
      Assess (agent/policy.py): evidence → calibrated probability, independent-evidence count, pattern
                        ▼
      Action executor (agent/actions.py): permission table in code — agent executes auto only, L1/L2 pending
      Policy engine: R1–R10, §3a case vs report, §6 stopping, approval routes auto/L1/L2
         └─ uncertain → VERIFY_WITH_CUSTOMER / STEP_UP_AUTH → simulated reply → re-assess → final actions
                        ▼
      GraphRAG (agent/retrieval.py): graph-linked closed cases + TF-IDF typology memory + exact policy text
                        ▼
      Explain (agent/narrative.py): grounded summary + SAR narrative (template, or LLM rewrite with --llm)
                        ▼
      Case memory: InvestigationCase vertex + INV_* edges upserted to TigerGraph → found by the next case
```

The LLM never decides: verdicts and actions come from the deterministic, rule-citing policy engine; the LLM only
rewrites explanations from the retrieved facts.

## Key data engineering findings

* **card_id** is not a column. It is `customer_id + "-K" + rank of card6 within the customer` (missing first,
  then alphabetical) — reproduces 100% of card IDs in the closed cases and the case pack.
* **customer_id is an aggregate** (up to 14,932 transactions). The cardholder behaviour profile
  `customer_id + addr1 + (day − D1)` recovers individual habits (e.g. HHG-001: the same person pays ~$77 in
  region 444 every week since September).
* **Case-memory model**: LightGBM trained on the 5,565 closed cases (confirmed vs cleared + unflagged background)
  using Vesta's unnamed C/D/M/V/id features. Oct hold-out AUC 0.91 (risk score 0.865); fraud-vs-cleared 0.88
  (risk score 0.05). It is one evidence item, never a verdict.
* **Every customer-reported dispute in the closed cases was confirmed fraud**; all 900 cleared cases were model
  alerts. Disputes therefore carry strong prior weight unless the cardholder's own habit explains them (R7).

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env            # fill TG_HOST / TG_SECRET (or user+password)
DATA=/path/to/HHGOA_IEEE        # folder with transactions*.csv, identity.csv, closed_cases_history.csv, case_pack.csv

python scripts/01_build_features.py        --data-dir $DATA   # feature store + card_id + cardholder profile
python scripts/02_train_case_memory_model.py --data-dir $DATA # case-memory model (≈3 GB RAM)
python scripts/03_export_graph_csv.py      --data-dir $DATA   # loading files
python scripts/04_load_tigergraph.py --steps schema,load,queries

python run_cases.py --data-dir $DATA --backend tigergraph      # GSQL via pyTigerGraph, cases written to graph
python run_cases.py --data-dir $DATA --backend mcp --llm       # GSQL via TigerGraph MCP + grounded LLM text
python run_cases.py --data-dir $DATA --backend local           # offline reproduction (same logic)

python scripts/validate_answers.py $DATA
python scripts/05_check_graph.py                             # validate the load
python scripts/backtest.py --data-dir $DATA --n 300           # graph-evidence-only backtest
python scripts/demo_uncertainty.py --data-dir $DATA --case HHG-002   # recommendation changes with evidence
python -m pytest -q tests                                     # permissions + answer contract
python scripts/monitor.py --data-dir $DATA                    # optional: monitoring beyond the 20 cases
python ui/build_case_view.py && open ui/case_view.html
```

## Repository

```
agent/        investigator (agent loop), actions (code-enforced permissions + mock APIs), backends (TigerGraph / MCP / local), detectors, policy, retrieval, narrative
graph/       schema.gsql, loading_job.gsql, queries.gsql
scripts/      01–04 pipeline, validate_answers.py
rag/    fraud policy + pattern text used for GraphRAG grounding
cases/        the 20 answer files
ui/           case_view.html (offline, one case at a time), traces/ (per-case steps, tool log, decision history)
tests/        permission (adversarial) tests + answer-contract tests
extra_cases/  optional monitor output (Innovation)
docs/         BLOG.md, DEMO_SCRIPT.md
```

## Assumptions (stated in every case file)

* Customer / analyst replies are simulated. The reply is a deterministic function of the pre-request evidence
  (risk alerts: p < 0.40 confirms, 0.40–0.60 no reply, ≥ 0.60 denies; disputes: p < 0.30 recognises the charge,
  otherwise re-confirms the denial) and is written into `evidence_requests.assumed_response`.
* Evidence is gathered as of the case's `opened_at`; nothing later is used.
* `written_to_graph` is true only when the run used the TigerGraph backend and the upsert succeeded.

Dataset: IEEE-CIS Fraud Detection (Vesta Corporation) with additions by TigerGraph for HHGOA 2026. The public
Kaggle files were not used.
