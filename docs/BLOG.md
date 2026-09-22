# Blog draft — "A risk score is a reason to look: building Fraud Detection Agent on TigerGraph"

## What we built
Fraud Detection Agent is a fraud-investigation agent. Give it an alert — a model score, a customer complaint or an analyst's
hunch — and it investigates the way an analyst would: it pulls the card's history, the real cardholder's habits,
the device and everyone else who used it, and the bank's own closed cases. It decides how sure it is, asks the
customer when it is not sure enough, recommends actions with the right approval route, files a suspicious
activity report only when the policy calls for one, and writes the investigation back into the graph so the next
case can find it.

## The data taught us three things before we wrote any agent code
1. **The score lies where it matters.** Among alerts the bank already closed, the risk score separates confirmed
   fraud from cleared false alarms with an AUC of 0.05. The high scores *are* the false alarms.
2. **A "customer" is often thousands of people.** Some customer IDs hold 14,932 transactions. Combining
   customer, billing region and Vesta's D1 day-delta gives a behaviour profile per real cardholder — HHG-001 turned
   out to be someone who spends ~$77 in the same region every week.
3. **The labels are in the case notes.** 5,565 closed cases became (a) a LightGBM case-memory model (AUC 0.88 on
   fraud-vs-cleared), (b) a retrieval corpus, and (c) two undocumented typologies we then hunted for.

## Architecture
(Insert the diagram from README.) TigerGraph holds customers, cards, transactions, device profiles, email
domains, billing regions, cardholder profiles, closed cases and our own InvestigationCase vertices. Eight
installed GSQL queries are the agent's tools, exposed through the TigerGraph MCP server. Python detectors turn
query results into evidence; a deterministic policy engine turns evidence into actions; GraphRAG hands the LLM
only the distilled facts, the exact policy paragraphs and similar closed-case notes.

## How TigerGraph is used
* `shared_device_cards` — a two-hop card → device → card traversal that exposed a Samsung SM-G935F ring on 20
  cards in eight days (HHG-014) and a five-card $100 ring on a device seen only five times ever (HHG-019).
* `device_footprint` separates rare device profiles (signal) from generic ones like "Windows | Chrome" (noise).
* `cardholder_txns` walks BEHAVES_AS edges to the real person's history.
* `cases_by_device` / `cases_by_card` retrieve memory; `case_memory` finds our own earlier investigations.
* Every investigation is upserted as an InvestigationCase with edges to the card, affected transactions,
  connected cards, devices and the closed cases it relied on.

## Agentic capabilities
Trigger handling for three alert types · tool use over MCP · uncertainty assessment with an independent-evidence
count · controlled evidence requests (verify, step-up) with recorded assumptions · before/after next best actions
· §6 stopping rules · approval routing (auto / L1 / L2) · SAR vs case-only decisions · case memory that grows as
cases close · full step and tool trace per case.

## What we learned
Graph context beats a better score: the three cases that most needed the graph (structuring, two device rings)
all had low or unremarkable risk scores. Most "suspicious" alerts were explained by the cardholder's own history.

## What we would improve
Vector search over closed-case narratives inside TigerGraph (TigerVector), community detection (WCC/Louvain) to
pre-compute rings nightly, real customer-verification webhooks, and calibration of the probability model against
the answer key.

---

# Demo script (3–5 minutes)

1. **0:00 Hook** — "The bank's risk score separates fraud from false alarms with AUC 0.05. We don't start from the
   score." Show the 20-case ledger in the dashboard: 8 fraud, 12 legitimate, 3 SARs.
2. **0:30 Architecture** — README diagram; TigerGraph Savanna schema view; the eight installed queries.
3. **1:00 Live run** — `python run_cases.py --backend mcp --cases HHG-019`; show MCP tool calls streaming.
4. **1:40 HHG-019** — flagged $99.92 looks like one odd purchase. The two-hop query finds the same rare device on
   five cards, all ~$100, all verizon.net. Fraud, R6: block (L1), case, SAR (L2), monitor connected cards.
5. **2:30 HHG-002** — uncertainty: single signal, p 0.18. Initial = CREATE_CASE + VERIFY (R1). Simulated reply →
   final CLOSE_NO_FRAUD. Show before/after and what changed.
6. **3:10 HHG-006** — undocumented structuring: four purchases under $500 in 30 minutes, matched to five closed
   September cases. Show the SAR narrative.
7. **3:50 Case memory** — open the InvestigationCase vertices in TigerGraph; show HHG-014 finding the ring's earlier
   closed cases. Close on the tool log and the validator output.
