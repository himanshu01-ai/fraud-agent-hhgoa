"""
Phase-3 check: do the graph detectors separate confirmed fraud from cleared alerts BEFORE any LLM is involved?
Replays a sample of October closed cases through the same investigator with:
  * trigger forced to 'risk_score' (no dispute prior)  * the case-memory model signal switched OFF (it was trained
    on these cases)  -> measures graph evidence alone.
  python scripts/backtest.py --data-dir $DATA --n 300
"""
import argparse, glob, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score
from agent.backends import LocalBackend
from agent.retrieval import Retriever
from agent.investigator import Investigator

ap = argparse.ArgumentParser()
ap.add_argument('--data-dir', required=True)
ap.add_argument('--n', type=int, default=300)
a = ap.parse_args()
cc_path = glob.glob(os.path.join(a.data_dir, '*closed_cases_history.csv'))[0]
cc = pd.read_csv(cc_path)
g = LocalBackend(cc_path=cc_path, memory='data/backtest_memory.json')
g.tx['p_model'] = np.nan                       # graph evidence only
agent = Investigator(g, Retriever(cc))
oct_ = cc[cc.opened_at >= '2016-10-01']
sample = pd.concat([oct_[oct_.outcome == 'cleared'].sample(min(a.n // 2, (oct_.outcome == 'cleared').sum()), random_state=1),
                    oct_[oct_.outcome == 'confirmed_fraud'].sample(a.n // 2, random_state=1)])
rows = []
for r in sample.itertuples():
    t = str(r.txn_ids).split('|')[-1]
    case = {'case_id': r.case_id, 'opened_at': r.opened_at, 'trigger_type': 'risk_score',
            'trigger_text': f'backtest of {r.case_id}', 'flagged_txn_id': int(t), 'card_id': r.card_id,
            'customer_id': r.customer_id}
    g.exclude = r.case_id
    ans, tr = agent.run(case)
    prov = [x['detail'] for x in tr['trace'] if x['name'] == 'assess'][0].split('provisional pattern ')[1].split(',')[0]
    rows.append((r.outcome == 'confirmed_fraud', tr['p_initial'], r.pattern, prov))
d = pd.DataFrame(rows, columns=['fraud', 'p', 'true_pattern', 'pred_pattern'])
print('graph-evidence-only AUC (fraud vs cleared):', round(roc_auc_score(d.fraud, d.p), 3))
print(d.groupby('fraud').p.describe()[['mean', '50%']])
f = d[d.fraud]
print('pattern agreement on confirmed fraud:', round((f.true_pattern == f.pred_pattern).mean(), 3))
with pd.option_context('display.width', 200):
    print(pd.crosstab(f.true_pattern, f.pred_pattern))
