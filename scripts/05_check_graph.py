"""
Phase-2 validation: never trust a silent load. Compares TigerGraph counts with the feature store and spot-checks
known cases through the installed queries.
  python scripts/05_check_graph.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from agent.tg_conn import connect

conn = connect()
tx = pd.read_pickle('data/tx_core.pkl')
expect = {'Txn': len(tx), 'Card': tx.card_id.nunique(), 'Customer': tx.customer_id.nunique(),
          'DeviceProfile': tx.device_profile.nunique(), 'ClosedCase': 5565}
ok = True
for vt, n in expect.items():
    got = conn.getVertexCount(vt)
    flag = 'OK ' if got == n else 'BAD'
    ok &= got == n
    print(f'{flag} {vt:14s} graph={got:>8} expected={n:>8}')
checks = [
    ('card_txns', {'c': 'C07297-K1', 't_from': '2016-11-21 19:00:00', 't_to': '2016-11-21 21:00:00'}, 'T', 4,
     'HHG-006 structuring episode (4 txns)'),
    ('device_footprint', {'d': 'SM-G935F Build/NRD90M | Android 7.0 | chrome 62.0 for android | 1920x1080'}, None, None,
     'SM-G935F ring footprint (~52 customers)'),
    ('cases_by_device', {'d': 'SM-G935F Build/NRD90M | Android 7.0 | chrome 62.0 for android | 1920x1080'}, 'C', 4,
     'ring closed cases CC-2649/2971/2985/3035'),
]
for q, params, key, n, label in checks:
    r = conn.runInstalledQuery(q, params)
    got = sum(len(b.get(key, [])) for b in r) if key else r
    good = (got >= n) if n else True
    ok &= good
    print(('OK ' if good else 'BAD'), label, '->', got if key else str(r)[:160])
print('\nGRAPH VALID' if ok else '\nFIX THE LOAD BEFORE BUILDING ON IT')
