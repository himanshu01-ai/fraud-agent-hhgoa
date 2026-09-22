"""
Step 2 - Learn from the bank's own closed cases ("case memory model").

The bank's risk_score is weak among alerts: on October hold-out cases its AUC for
confirmed-fraud vs cleared is ~0.05 (it is *anti*-informative - cleared cases are exactly
the high-score false alarms).  We train a LightGBM model on:
    label 1 = transactions in confirmed_fraud closed cases (Jul-Oct)
    label 0 = transactions in cleared closed cases + 200k random unflagged Jul-Oct transactions
Features = Vesta's unnamed C/D/M/V/id features + behavioural aggregates (no outcome leakage,
no public Kaggle labels).  Result on the Oct hold-out: AUC 0.91 overall, 0.88 fraud-vs-cleared.

The score ("p_model") is ONE piece of evidence for the agent, never a verdict.
Output: data/scores.pkl (TransactionID, p_model), data/model.txt
Usage : python scripts/02_train_case_memory_model.py --data-dir /path/to/HHGOA_IEEE
"""
import argparse, glob, os
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import roc_auc_score

VCOLS = [f'V{i}' for i in list(range(1, 138)) + list(range(279, 322))]
CAT = ['ProductCD', 'card4', 'card6', 'P_emaildomain', 'R_emaildomain', 'M1', 'M2', 'M3', 'M4', 'M5', 'M6',
       'M7', 'M8', 'M9', 'id_15', 'id_23', 'id_12', 'id_16', 'id_28', 'id_29', 'id_34', 'id_35', 'id_36',
       'id_37', 'id_38', 'DeviceType', 'channel']


def read_v(data_dir):
    single = os.path.join(data_dir, 'transactions.csv')
    use = ['TransactionID'] + VCOLS
    dt = {v: 'float32' for v in VCOLS}
    if os.path.exists(single):
        return pd.read_csv(single, usecols=use, dtype=dt)
    parts = sorted(glob.glob(os.path.join(data_dir, '*transactions-part-*.csv')))
    hdr = pd.read_csv(parts[0], nrows=0).columns.tolist()
    out = [pd.read_csv(p, usecols=use, dtype=dt) if i == 0 else
           pd.read_csv(p, header=None, names=hdr, usecols=use, dtype=dt) for i, p in enumerate(parts)]
    return pd.concat(out, ignore_index=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-dir', required=True)
    ap.add_argument('--core', default='data/tx_core.pkl')
    a = ap.parse_args()

    tx = pd.read_pickle(a.core).sort_values('TransactionID').reset_index(drop=True)
    v = read_v(a.data_dir).sort_values('TransactionID').reset_index(drop=True)
    assert (v.TransactionID.values == tx.TransactionID.values).all()
    df = pd.concat([tx, v.drop(columns=['TransactionID'])], axis=1)
    del tx, v

    for c in CAT:
        df[c] = df[c].astype('category')
    df['hour'] = df.ts.dt.hour
    df['cents'] = (df.TransactionAmt * 100 % 100).round()
    g = df.groupby('uid', observed=True).TransactionAmt
    df['uid_n'] = g.transform('size')
    df['uid_amt_mean'] = g.transform('mean')
    df['amt_over_uid'] = df.TransactionAmt / df.uid_amt_mean
    df['uid_email_n'] = df.groupby('uid').P_emaildomain.transform('nunique')
    df['uid_dev_n'] = df.groupby('uid').device_profile.transform('nunique')
    df['cust_n'] = df.groupby('customer_id').TransactionID.transform('size')
    df['dev_cust_n'] = df.groupby('device_profile').customer_id.transform('nunique')

    cc = pd.read_csv(glob.glob(os.path.join(a.data_dir, '*closed_cases_history.csv'))[0])
    m = cc.assign(t=cc.txn_ids.astype(str).str.split('|')).explode('t')
    m['t'] = m.t.astype(int)
    pos = set(m[m.outcome == 'confirmed_fraud'].t)
    neg = set(m[m.outcome == 'cleared'].t)
    df['y'] = np.nan
    df.loc[df.TransactionID.isin(neg), 'y'] = 0
    bg = df[(df.ts < '2016-11-01') & ~df.TransactionID.isin(pos | neg)].sample(200000, random_state=0).index
    df.loc[bg, 'y'] = 0
    df.loc[df.TransactionID.isin(pos), 'y'] = 1

    drop = {'TransactionID', 'ts', 'customer_id', 'card_id', 'device_profile', 'uid', 'y', 'risk_score',
            'TransactionDT'}
    feats = [c for c in df.columns if c not in drop]
    lab = df[df.y.notna()]
    trn, val = lab[lab.ts < '2016-10-01'], lab[lab.ts >= '2016-10-01']
    p = dict(objective='binary', learning_rate=0.05, num_leaves=63, min_child_samples=50,
             feature_fraction=0.5, bagging_fraction=0.8, bagging_freq=1, verbose=-1)
    mdl = lgb.train(p, lgb.Dataset(trn[feats], trn.y), 600, valid_sets=[lgb.Dataset(val[feats], val.y)],
                    callbacks=[lgb.early_stopping(50, verbose=False)])
    pv = mdl.predict(val[feats])
    vv = val.TransactionID.isin(pos | neg).values
    print(f'hold-out AUC model={roc_auc_score(val.y, pv):.3f} risk_score={roc_auc_score(val.y, val.risk_score):.3f}')
    print(f'fraud-vs-cleared AUC model={roc_auc_score(val.y[vv], pv[vv]):.3f} '
          f'risk_score={roc_auc_score(val.y[vv], val.risk_score[vv]):.3f}')
    full = lgb.train(p, lgb.Dataset(lab[feats], lab.y), mdl.best_iteration)
    out = pd.DataFrame({'TransactionID': df.TransactionID, 'p_model': full.predict(df[feats])})
    out.to_pickle('data/scores.pkl')
    full.save_model('data/model.txt')
    print('scores ->', 'data/scores.pkl')


if __name__ == '__main__':
    main()
