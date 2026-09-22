"""Validate cases/*.json against the README answer format and the dataset IDs."""
import glob, json, sys
import pandas as pd

ACTIONS = {'ALLOW_TRANSACTION', 'DECLINE_TRANSACTION', 'MONITOR_CARD', 'MONITOR_CONNECTED_CARDS', 'WARN_CUSTOMER',
           'VERIFY_WITH_CUSTOMER', 'STEP_UP_AUTH', 'BLOCK_CARD', 'BLOCK_ALL_CARDS', 'GENERATE_REPORT', 'CREATE_CASE',
           'FILE_REPORT', 'ESCALATE_TO_ANALYST', 'CLOSE_NO_FRAUD'}
PATTERNS = {'card_testing', 'card_not_present_fraud', 'card_not_present_new_device', 'out_of_region_use',
            'account_takeover', 'undocumented', 'none'}
tx = pd.read_pickle('data/tx_core.pkl')[['TransactionID', 'TransactionAmt', 'card_id', 'customer_id', 'device_profile']]
cc = pd.read_csv(glob.glob(sys.argv[1] + '/*closed_cases_history.csv')[0])
TX, CARDS, CUST, DEV, CC = set(tx.TransactionID.astype(str)), set(tx.card_id), set(tx.customer_id), set(tx.device_profile.dropna()), set(cc.case_id)
amt = dict(zip(tx.TransactionID.astype(str), tx.TransactionAmt))
bad = 0
for f in sorted(glob.glob('cases/*.json')):
    a = json.load(open(f)); c = a['case']; err = []
    for k in ['case_id', 'case', 'evidence_requests', 'next_best_actions', 'sar', 'stop_reason', 'tool_calls', 'tokens', 'latency_s']:
        if k not in a: err.append('missing ' + k)
    if c['pattern'] not in PATTERNS: err.append('pattern')
    if c['pattern'] == 'undocumented' and not c['pattern_description']: err.append('pattern_description')
    for t in c['affected_txn_ids']:
        if t not in TX: err.append('txn ' + t)
    for k in c['connected_card_ids']:
        if k not in CARDS: err.append('card ' + k)
    for d in c['connected_device_profiles']:
        if d not in DEV: err.append('device ' + d)
    for s in c['similar_prior_cases']:
        if s not in CC: err.append('cc ' + s)
    if abs(sum(amt[t] for t in c['affected_txn_ids']) - c['exposure_usd']) > 0.05: err.append('exposure')
    if c['verdict'] == 'legitimate' and (c['affected_txn_ids'] or c['exposure_usd'] or a['sar']['file']): err.append('legit rules')
    for ph in ['initial', 'final']:
        for x in a['next_best_actions'][ph]:
            if x['action'] not in ACTIONS: err.append('action ' + x['action'])
    fr = any(x['action'] == 'FILE_REPORT' for x in a['next_best_actions']['final'])
    if fr != a['sar']['file']: err.append('sar/FILE_REPORT mismatch')
    if not a['evidence_requests'] and a['next_best_actions']['initial'] != a['next_best_actions']['final']: err.append('initial!=final')
    for s in a['sar']['subjects']:
        if s not in CARDS | CUST | DEV: err.append('subject ' + s)
    print(a['case_id'], 'OK' if not err else err); bad += bool(err)
print('files with errors:', bad)
