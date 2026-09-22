"""
Step 1 - Build the core transaction feature store from the HHGOA dataset.

Input  : DATA_DIR with transactions.csv (or transactions-part-*.csv), identity.csv,
         closed_cases_history.csv, case_pack.csv
Output : data/tx_core.pkl   (590,742 rows, ~75 columns, used by the agent + graph export)

Key derivations (all verified against the dataset):
  * card_id   = customer_id + "-K" + rank of card6 within the customer (missing card6 first,
                then alphabetical).  Reproduces 100% of card_ids in closed_cases_history and
                case_pack (15,000+ transactions checked).
  * device_profile = DeviceInfo | OS (id_30) | browser (id_31) | screen (id_33), as the README defines.
  * uid (cardholder behaviour profile) = customer_id + addr1 + (day - D1).  D1 behaves like
    "days since the card relationship started", so this separates the real cardholders that
    share one customer_id (some customer_ids hold >10,000 transactions).
Usage: python scripts/01_build_features.py --data-dir /path/to/HHGOA_IEEE
"""
import argparse, glob, os
import numpy as np
import pandas as pd

KEEP = (['TransactionID', 'TransactionDT', 'TransactionAmt', 'ProductCD']
        + [f'card{i}' for i in range(1, 7)]
        + ['addr1', 'addr2', 'dist1', 'dist2', 'P_emaildomain', 'R_emaildomain']
        + [f'C{i}' for i in range(1, 15)] + [f'D{i}' for i in range(1, 16)]
        + [f'M{i}' for i in range(1, 10)]
        + ['customer_id', 'ts', 'channel', 'risk_score'])
ID_KEEP = ['TransactionID', 'device_profile', 'DeviceType', 'id_15', 'id_23', 'id_34', 'id_12', 'id_16',
           'id_28', 'id_29', 'id_35', 'id_36', 'id_37', 'id_38', 'id_01', 'id_02', 'id_19', 'id_20']


def read_transactions(data_dir):
    single = os.path.join(data_dir, 'transactions.csv')
    if os.path.exists(single):
        return pd.read_csv(single, usecols=KEEP, low_memory=False)
    parts = sorted(glob.glob(os.path.join(data_dir, '*transactions-part-*.csv')))
    if not parts:
        raise SystemExit('transactions.csv or transactions-part-*.csv not found')
    hdr = pd.read_csv(parts[0], nrows=0).columns.tolist()
    out = []
    for i, p in enumerate(parts):
        if i == 0:
            out.append(pd.read_csv(p, usecols=KEEP, low_memory=False))
        else:  # split parts 2..n have no header row
            out.append(pd.read_csv(p, header=None, names=hdr, usecols=KEEP, low_memory=False))
    return pd.concat(out, ignore_index=True)


def find(data_dir, name):
    hits = glob.glob(os.path.join(data_dir, f'*{name}'))
    if not hits:
        raise SystemExit(f'{name} not found in {data_dir}')
    return hits[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-dir', required=True)
    ap.add_argument('--out', default='data/tx_core.pkl')
    a = ap.parse_args()

    tx = read_transactions(a.data_dir)
    tx['ts'] = pd.to_datetime(tx['ts'])
    print('transactions', len(tx))

    idn = pd.read_csv(find(a.data_dir, 'identity.csv'), low_memory=False)
    s = lambda x: 'NA' if pd.isna(x) else str(x)
    idn['device_profile'] = [f'{s(d)} | {s(o)} | {s(b)} | {s(sc)}' for d, o, b, sc in
                             zip(idn.DeviceInfo, idn.id_30, idn.id_31, idn.id_33)]
    tx = tx.merge(idn[ID_KEEP], on='TransactionID', how='left')

    # card_id derivation (verified 100% against closed cases + case pack)
    key = tx.card6.astype(object).fillna('~').astype(str)
    u = pd.DataFrame({'c': tx.customer_id, 'key': key, 'nf': tx.card6.notna()}).drop_duplicates()
    u = u.sort_values(['c', 'nf', 'key'])
    u['K'] = u.groupby('c').cumcount() + 1
    kmap = dict(zip(zip(u.c, u.key), u.K))
    tx['card_id'] = [f'{c}-K{kmap[(c, k)]}' for c, k in zip(tx.customer_id, key)]

    # cardholder behaviour profile
    day = tx.TransactionDT // 86400
    tx['uid'] = (tx.customer_id.astype(str) + '_' + tx.addr1.astype(str) + '_' + (day - tx.D1).astype(str))
    tx.loc[tx.D1.isna() | tx.addr1.isna(), 'uid'] = np.nan

    for c in tx.select_dtypes('float64').columns:
        tx[c] = tx[c].astype('float32')
    tx = tx.sort_values('ts').reset_index(drop=True)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    tx.to_pickle(a.out)
    print('cards', tx.card_id.nunique(), 'device profiles', tx.device_profile.nunique(), '->', a.out)


if __name__ == '__main__':
    main()
