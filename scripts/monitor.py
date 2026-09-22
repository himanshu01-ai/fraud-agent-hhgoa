"""
Optional (Innovation): autonomous monitoring of the exam period beyond the 20 cases.
Scans Nov-Dec week by week with ring_scan (rare device profiles hitting >= 3 cards), opens an analyst_request
alert on each affected card and investigates it with the same agent. Output: extra_cases/*.json
  python scripts/monitor.py --data-dir $DATA --max-cases 25
"""
import argparse, glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from agent.backends import LocalBackend, TigerGraphBackend
from agent.retrieval import Retriever
from agent.investigator import Investigator

ap = argparse.ArgumentParser()
ap.add_argument('--data-dir', required=True)
ap.add_argument('--backend', default='local', choices=['local', 'tigergraph'])
ap.add_argument('--max-cases', type=int, default=25)
a = ap.parse_args()
cc_path = glob.glob(os.path.join(a.data_dir, '*closed_cases_history.csv'))[0]
bench = set(pd.read_csv(glob.glob(os.path.join(a.data_dir, '*case_pack.csv'))[0]).card_id)
g = LocalBackend(cc_path=cc_path, memory='data/monitor_memory.json') if a.backend == 'local' else TigerGraphBackend(cc_path=cc_path)
agent = Investigator(g, Retriever(pd.read_csv(cc_path)))
os.makedirs('extra_cases', exist_ok=True)
n, seen = 0, set()
for start in pd.date_range('2016-11-01', '2016-12-25', freq='7D'):
    end = start + pd.Timedelta('7D')
    rings = g.ring_scan(start, end) if hasattr(g, 'ring_scan') else pd.DataFrame()
    for r in rings.itertuples():
        if r.n_new < 0.8 * r.n_txns and r.n_proxy < 0.8 * r.n_txns:
            continue
        for card in r.cards:
            if card in bench or card in seen or n >= a.max_cases:
                continue
            t = g.device_txns(r.device_profile, start, end)
            t = t[t.card_id == card].iloc[-1]
            case = {'case_id': f'MON-{n + 1:03d}', 'opened_at': str(t.ts + pd.Timedelta('6h')),
                    'trigger_type': 'analyst_request', 'flagged_txn_id': int(t.TransactionID), 'card_id': card,
                    'customer_id': t.customer_id,
                    'trigger_text': f'Monitor: device profile "{r.device_profile}" hit {len(r.cards)} cards between '
                                    f'{start:%Y-%m-%d} and {end:%Y-%m-%d}. Review transaction {int(t.TransactionID)}.'}
            ans, _ = agent.run(case)
            json.dump(ans, open(f'extra_cases/{case["case_id"]}.json', 'w'), indent=2)
            seen.add(card); n += 1
            print(case['case_id'], card, ans['case']['verdict'], ans['case']['pattern'], ans['sar']['file'])
print('monitor opened', n, 'cases -> extra_cases/')
