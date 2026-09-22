# Data dictionary — HHGOA IEEE-CIS fraud dataset

Every number on this page was computed from the dataset on 2026-09-23, not recalled. The commands are in
[How these numbers were produced](#how-these-numbers-were-produced) at the bottom; re-run them if you doubt a figure.

Dataset location on the build machine: **`D:`** — pass it with **no trailing slash**. `scripts/validate_answers.py`
builds its path by string concatenation, so `D:/` yields `D://closed_cases_history.csv`, which pandas reads as a URL
scheme and fails with `ImportError: Import fsspec failed`. That error is a path artifact, not a missing package.

---

## 1. Files

| File | Rows | Size | One row is |
|---|---:|---:|---|
| `transactions.csv` | 590,742 | 707.9 MB | one card transaction, the full six-month spine |
| `transactions-part-001.csv` | 209,294 | 252.7 MB | same, **with** a header row |
| `transactions-part-002.csv` | 212,332 | 252.7 MB | same, **no header** — reuse part-001's columns |
| `transactions-part-003.csv` | 169,116 | 201.9 MB | same, **no header** |
| `identity.csv` | 144,432 | 26.7 MB | the device/session fingerprint for **one** transaction, joined on `TransactionID` |
| `closed_cases_history.csv` | 5,565 | 2.7 MB | one investigation the bank already closed, with its outcome |
| `case_pack.csv` | 20 | 4 KB | one benchmark case to investigate — this is what we are scored on |
| `data/tx_core.pkl` | 590,742 × 77 cols | 259 MB | built artifact: transactions ⨝ identity + the three derived keys |

The three parts sum to exactly 590,742, matching the single file. **Parts 002 and 003 carry no header row** — a
line count of those files is the row count, while part-001's is one higher. `scripts/01_build_features.py` prefers
`transactions.csv` when present and otherwise reads the parts, passing `header=None, names=<part-001 columns>` for
parts 2..n.

`identity.csv` covers only **24.45%** of transactions (144,432 / 590,742). Every device column is therefore null for
about three quarters of rows — that is coverage, not missing data, and the detectors must treat "no identity row"
as unknown rather than as a negative signal.

---

## 2. Columns we use

Null rates are over all 590,742 rows of `data/tx_core.pkl`.

### Transaction identity
| Column | Null | Distinct | Meaning |
|---|---:|---:|---|
| `TransactionID` | 0.00% | 590,742 | primary key, unique per row |
| `TransactionDT` | 0.00% | 574,993 | seconds from an arbitrary epoch; `// 86400` gives the day index used by `uid` |
| `TransactionAmt` | 0.00% | 34,885 | amount in USD |
| `ProductCD` | 0.00% | 5 | product class — W 439,670 · C 68,721 · R 37,699 · H 33,024 · S 11,628 |

### Card
| Column | Null | Distinct | Meaning |
|---|---:|---:|---|
| `card1` | 0.00% | 13,553 | issuer-side card identifier; **exactly matches the `customer_id` cardinality** |
| `card2` | 1.51% | 500 | issuer sub-code |
| `card3` | 0.26% | 114 | country/region code |
| `card4` | 0.27% | 4 | network — visa, mastercard, amex, discover |
| `card5` | 0.72% | 119 | issuing bank code |
| `card6` | 0.27% | 4 | card type — debit, credit, charge, debit or credit. **Drives `card_id`.** |

### Address and email
| Column | Null | Distinct | Meaning |
|---|---:|---:|---|
| `addr1` | 11.13% | 332 | billing region. Used by the region detector and by `uid` |
| `addr2` | 11.13% | 74 | billing country |
| `dist1` | 59.67% | 2,651 | distance proxy (billing vs transaction) |
| `dist2` | 93.63% | 1,751 | second distance proxy — too sparse to rely on |
| `P_emaildomain` | 15.99% | 59 | purchaser email domain — an `EmailDomain` vertex |
| `R_emaildomain` | 76.73% | 60 | recipient email domain |

### C counters (1–14)
All **0.00% null**, 27–1,657 distinct. Anonymised counts of entities linked to the card (addresses, phones, emails).
`C1`, `C13`, `C14` are the highest-cardinality and the most useful to the model. Their meanings are not published;
we use them as model features only, never as a stated reason in an evidence line.

### D counters (1–15)
Day-deltas since some prior event. **`D1` is the one we depend on** — 0.21% null, 641 distinct, and it behaves as
"days since the card relationship started", which is what makes `uid` work. The rest range from 12.90% null (`D10`)
to 93.41% (`D7`); anything above ~50% null is model-only.

### M flags (1–9)
Boolean match indicators (name/address/etc. agree between card and transaction). 28.70% null (`M6`) to 59.36%
(`M5`). `M4` has 3 values, the rest 2. `M4` and `M6` are carried onto the `Txn` vertex because the narrative cites them.

### V block
The dataset keeps all 339 original `V*` columns. **We deliberately do not load them** into `tx_core.pkl` — they are
unlabelled engineered features with no investigative meaning, so they cannot appear in an evidence line, and
dropping them is what keeps the feature store at 77 columns instead of ~430.

### Identity / device
| Column | Null | Distinct | Meaning |
|---|---:|---:|---|
| `device_profile` | 75.55% | 9,706 | **derived** — see §3 |
| `DeviceType` | 76.13% | 2 | desktop / mobile |
| `id_23` | 99.10% | 3 | proxy type. Rare, but decisive: this is what flags anonymous/hidden proxies |
| `id_30` / `id_31` / `id_33` | — | — | OS / browser / screen resolution; consumed by `device_profile`, not kept separately |
| `id_01`, `id_02` | 75.55% / 76.12% | 77 / 115,655 | anonymised session scores |
| `id_12`, `id_15`, `id_16`, `id_28`, `id_29`, `id_35`–`id_38` | 75.55–78.08% | 2–3 | match/found flags |
| `id_19`, `id_20` | 76.39% | 522 / 394 | anonymised session attributes |
| `id_34` | 86.81% | 4 | anonymised session attribute |

### HHGOA additions (not in the public IEEE-CIS data)
| Column | Null | Distinct | Meaning |
|---|---:|---:|---|
| `customer_id` | 0.00% | 13,553 | the bank's customer. **An aggregate, not a person — see §3.3** |
| `ts` | 0.00% | 574,993 | real calendar timestamp, 2016-07-02 → 2016-12-31 |
| `channel` | 0.00% | 2 | in_person 439,670 · online 151,072 |
| `risk_score` | 0.00% | 99 | the bank's existing detection model score. **Anti-informative — see §4** |

---

## 3. The three derived keys

These are built in `scripts/01_build_features.py`. They exist because the raw data has no usable notion of "a card"
or "a person", and the graph needs both.

### 3.1 `card_id` — the card
```
card_id = customer_id + "-K" + rank of card6 within that customer
          (rows with card6 missing rank first, then alphabetically)
```
**Why it exists:** the dataset never gives a card identifier, but `closed_cases_history` and `case_pack` both cite
one. Without reproducing their scheme exactly we could not join our transactions to the bank's own cases, and every
`connected_card_ids` answer would be wrong.

**The check — it reproduces their card_ids exactly:**

| Source | Matched | Total | Rate |
|---|---:|---:|---|
| `case_pack.csv` (flagged transaction → card_id) | 20 | 20 | **100.0%** |
| `closed_cases_history.csv` (every transaction in every case) | 14,955 | 14,955 | **100.0%** |

14,975 independent checks, zero mismatches. The derivation yields **14,317** distinct cards across 13,553 customers,
at most **3** cards per customer.

### 3.2 `device_profile` — the device
```
device_profile = DeviceInfo | id_30 | id_31 | id_33
                 (OS | browser | screen resolution, "NA" where absent)
```
**Why it exists:** there is no device ID. This four-part string is the closest stable fingerprint, and it is what
lets `ring_scan` find one device touching many cards. **9,706** distinct profiles.

Two cautions. **75.55%** of transactions have no identity row at all, so no profile. And **3.99%** of rows carry a
profile starting `NA | NA` — a generic shell shared by unrelated sessions. The ring detector must discount those or
it will invent rings out of missing data.

### 3.3 `uid` — the real cardholder
```
uid = customer_id + "_" + addr1 + "_" + (TransactionDT // 86400 - D1)
      null where D1 or addr1 is null
```
**Why it exists: `customer_id` is an aggregate, not a person.** The evidence:

| Check | Value |
|---|---:|
| Distinct `customer_id` | 13,553 |
| **Max transactions under one `customer_id`** | **14,932** (customer `C13440`) |
| Distinct `uid` inside that one customer_id | **3,789** |
| Distinct `card_id` inside it | 2 |
| Distinct `addr1` inside it | 57 |

One `customer_id` holding 14,932 transactions across 57 billing regions on 2 cards is not one shopper. `D1` behaves
as "days since the card relationship started", so `day − D1` is constant for a given relationship and separates the
real cardholders sharing that identifier. The split gives **202,440** distinct uids, median **1** transaction each,
max **1,401**.

**If we profiled "normal behaviour" per `customer_id` instead of per `uid`, the baseline for C13440 would average
3,789 unrelated people** — every genuine anomaly would vanish into the noise. That is the whole reason this key exists.
`uid` is null for **11.31%** of rows (missing `D1` or `addr1`); those fall back to card-level history.

---

## 4. `closed_cases_history.csv` — the bank's own memory

5,565 closed investigations, July–November 2016. This is the corpus GraphRAG retrieves from and the label source
for the case-memory model.

| outcome | count |
|---|---:|
| confirmed_fraud | 4,665 |
| cleared | 900 |

| pattern | count |
|---|---:|
| card_not_present_fraud | 1,404 |
| account_takeover | 1,205 |
| card_not_present_new_device | 1,076 |
| out_of_region_use | 955 |
| none (the cleared cases) | 900 |
| card_testing | 16 |
| **undocumented** | **9** |

`report_filed`: No 5,168 · Yes 397. Exposure: total \$2,072,387.77, median \$117.09, max \$35,031.56.
Transactions per case: median 1, max 356.

### The risk score is anti-informative — recomputed

Over **all 14,955** transactions belonging to a confirmed_fraud or cleared closed case:

```
risk_score AUC, confirmed_fraud vs cleared = 0.057
  mean risk_score, confirmed_fraud = 0.474
  mean risk_score, cleared         = 0.881
```

An AUC of 0.057 is not "weak", it is **strongly inverted**: cleared alerts score *higher* than real fraud. The
cleared cases are exactly the high-score false alarms the bank already looked at and dismissed. This is the single
most important fact about the dataset — **a high `risk_score` is a reason to look, never a reason to decide**, and
any detector that leans on it will invert its own verdict.

For reference, `scripts/02_train_case_memory_model.py` reports 0.052 on the October hold-out slice alone; 0.057 here
is the same statistic over the whole history. The trained model reaches **0.880** on that comparison and **0.912**
overall.

---

## 5. Time windows

| Window | Range |
|---|---|
| All transactions | 2016-07-02 00:02:21 → 2016-12-31 23:58:54 |
| **History** — closed cases opened | 2016-07-02 07:17:26 → 2016-11-02 02:00:37 |
| History — closed cases closed | 2016-07-04 02:10:20 → 2016-11-06 23:39:58 |
| **Exam** — the 20 benchmark cases opened | 2016-11-12 00:46:24 → 2016-12-29 07:53:54 |

The two windows **do not overlap**: the last closed case was opened 2016-11-02, the first benchmark case
2016-11-12 — a ten-day gap. Splitting at the first benchmark case gives 450,793 history transactions and 139,949
exam-window transactions.

This is what makes the no-look-ahead rule enforceable: when investigating a case opened at `T`, every closed case is
legitimately in the past, and the agent must still refuse to read transactions after `T`. Benchmark triggers:
risk_score 11, customer_report 8, analyst_request 1.

---

## 6. How these numbers were produced

```bash
# every figure above, from the real files
.venv/Scripts/python.exe scratch/profile.py "D:"      # files, null rates, derived keys, closed cases, windows
.venv/Scripts/python.exe scratch/undoc.py   "D:"      # exact part row counts, the 9 undocumented cases

# the pipeline that builds data/tx_core.pkl in the first place
.venv/Scripts/python.exe scripts/01_build_features.py --data-dir "D:"
#   -> transactions 590742 | cards 14317 | device profiles 9706
.venv/Scripts/python.exe scripts/02_train_case_memory_model.py --data-dir "D:"
#   -> hold-out AUC model=0.912 risk_score=0.865
#   -> fraud-vs-cleared AUC model=0.880 risk_score=0.052
```

The two profiling scripts are throwaway analysis, not part of the pipeline — they are reproduced in the PR body so
any teammate can paste and re-run them without hunting for a file.
