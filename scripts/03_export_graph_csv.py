"""
Step 3 - Export loading files for TigerGraph.
Output: data/graph/txn_*.csv (100k rows each), closed_cases.csv, cc_txn.csv, cc_conn.csv
Usage : python scripts/03_export_graph_csv.py --data-dir /path/to/HHGOA_IEEE
"""
import argparse, glob, os
import pandas as pd

COLS = ['TransactionID', 'ts', 'TransactionAmt', 'ProductCD', 'channel', 'addr1', 'addr2', 'P_emaildomain',
        'R_emaildomain', 'risk_score', 'p_model', 'id_15', 'id_23', 'M4', 'M6', 'card_id', 'customer_id',
        'device_profile', 'uid', 'card4', 'card6']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-dir', required=True)
    ap.add_argument('--chunk', type=int, default=100000)
    a = ap.parse_args()
    out = 'data/graph'
    os.makedirs(out, exist_ok=True)

    tx = pd.read_pickle('data/tx_core.pkl')
    sc = pd.read_pickle('data/scores.pkl') if os.path.exists('data/scores.pkl') else None
    tx = tx.merge(sc, on='TransactionID', how='left') if sc is not None else tx.assign(p_model=None)
    tx = tx[COLS].copy()
    tx['ts'] = tx.ts.dt.strftime('%Y-%m-%d %H:%M:%S')
    for c in ['addr1', 'addr2']:
        tx[c] = tx[c].map(lambda v: '' if pd.isna(v) else str(int(v)) + '.0')
    for i in range(0, len(tx), a.chunk):
        tx.iloc[i:i + a.chunk].to_csv(f'{out}/txn_{i // a.chunk:02d}.csv', index=False)

    cc = pd.read_csv(glob.glob(os.path.join(a.data_dir, '*closed_cases_history.csv'))[0])
    cc.fillna('').to_csv(f'{out}/closed_cases.csv', index=False)
    e = cc.assign(txn_id=cc.txn_ids.astype(str).str.split('|')).explode('txn_id')[['case_id', 'txn_id']]
    e.to_csv(f'{out}/cc_txn.csv', index=False)
    c2 = cc.dropna(subset=['connected_card_ids'])
    c2 = c2.assign(card_id=c2.connected_card_ids.str.split('|')).explode('card_id')[['case_id', 'card_id']]
    c2.to_csv(f'{out}/cc_conn.csv', index=False)
    print('exported', len(tx), 'txns,', len(cc), 'closed cases ->', out)


if __name__ == '__main__':
    main()
