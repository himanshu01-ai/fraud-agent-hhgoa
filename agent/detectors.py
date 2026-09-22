"""
Deterministic evidence detectors.  Each returns Signal objects built ONLY from rows the graph
returned, so every claim cites real IDs.  Weights are log-odds contributions used by assess.py.
"""
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

GENERIC = 'NA | NA | NA | NA'


@dataclass
class Signal:
    name: str
    weight: float            # + pushes to fraud, - pushes to legitimate
    claim: str
    ref: str
    entity_ids: list = field(default_factory=list)
    source: str = 'graph'
    episode: list = field(default_factory=list)      # txn ids that belong to the fraud episode
    connected_cards: list = field(default_factory=list)
    devices: list = field(default_factory=list)
    pattern: str = ''         # pattern this signal implies (if any)
    independent: bool = True


def _ids(d):
    return [str(int(x)) for x in d.TransactionID]


def money(x):
    return f'${x:,.2f}'


def card_stats(hist, asof_ts=None):
    h = hist
    old = h[h.ts < asof_ts - pd.Timedelta('7D')] if asof_ts is not None else h
    return dict(n=len(h), med=float(h.TransactionAmt.median()) if len(h) else np.nan,
                p90=float(h.TransactionAmt.quantile(.9)) if len(h) else np.nan,
                p95=float(h.TransactionAmt.quantile(.95)) if len(h) else np.nan,
                products=h.ProductCD.value_counts().to_dict(), regions=h.addr1.value_counts().to_dict(),
                emails=set(old.P_emaildomain.dropna()), devices=set(old.device_profile.dropna()),
                online=int((h.channel == 'online').sum()))


# ---------------------------------------------------------------- undocumented: structuring
def structuring(f, win, ref):
    w = win[(win.channel == 'online') & (win.TransactionAmt >= 400) & (win.TransactionAmt < 500) &
            ((win.ts - f.ts).abs() <= pd.Timedelta('60min'))]
    if len(w) >= 3 and f.TransactionID in set(w.TransactionID):
        span = (w.ts.max() - w.ts.min()).total_seconds() / 60
        devs = sorted(set(w.device_profile.dropna()))
        new = int((w.id_15 == 'New').sum())
        return [Signal('structuring_under_500', 4.0,
                       f'{len(w)} online purchases within {span:.0f} minutes, each just under $500 '
                       f'({", ".join(money(a) for a in w.TransactionAmt)}), total {money(w.TransactionAmt.sum())}; '
                       f'{new} of {len(w)} from device profiles marked New, {len(devs)} distinct devices. '
                       f'Amounts appear chosen to stay under a $500 authorization threshold.',
                       ref, _ids(w), episode=_ids(w), devices=devs, pattern='undocumented')]
    return []


# ---------------------------------------------------------------- pattern 1: card testing
def card_testing(f, win, ref):
    on = win[(win.channel == 'online') & (win.ts <= f.ts) & (win.ts >= f.ts - pd.Timedelta('3h'))]
    small = on[on.TransactionAmt < 10]
    if len(small) < 3:
        return []
    for i in range(len(small) - 2):
        grp = small[(small.ts >= small.ts.iloc[i]) & (small.ts <= small.ts.iloc[i] + pd.Timedelta('60min'))]
        if len(grp) >= 3 and f.TransactionAmt >= 3 * grp.TransactionAmt.max() and f.ts >= grp.ts.max():
            ep = _ids(grp) + [str(int(f.TransactionID))]
            return [Signal('card_testing_sequence', 4.0,
                           f'{len(grp)} online authorizations under $10 within one hour '
                           f'({", ".join(money(a) for a in grp.TransactionAmt)}) followed by a {money(f.TransactionAmt)} purchase',
                           ref, ep, episode=ep, pattern='card_testing')]
    return []


# ---------------------------------------------------------------- shared origin: device ring
def device_ring(f, dev_win, footprint, dev_cases, card_id, ref, ref2):
    if pd.isna(f.device_profile) or str(f.device_profile).startswith('NA | NA'):
        return []
    n_cards = dev_win.card_id.nunique()
    if footprint.get('n_customers', 999) > 60 or n_cards < 3:
        return []
    new_share = float((dev_win.id_15 == 'New').mean())
    anon_share = float(dev_win.id_23.isin(['IP_PROXY:ANONYMOUS', 'IP_PROXY:HIDDEN']).mean())
    amt_cluster = dev_win[(dev_win.TransactionAmt - f.TransactionAmt).abs() <= 0.03 * f.TransactionAmt].card_id.nunique()
    conf = dev_cases[dev_cases.outcome == 'confirmed_fraud'] if len(dev_cases) else dev_cases
    if not (new_share >= 0.8 or anon_share >= 0.8 or amt_cluster >= 3 or len(conf) >= 2):
        return []
    w = 3.5 + (1.0 if len(conf) >= 2 else 0.0)
    own = dev_win[dev_win.card_id == card_id]
    others = sorted(set(dev_win.card_id) - {card_id})
    parts = [f'Device profile "{f.device_profile}" (used by only {footprint.get("n_customers")} customers in the whole dataset) '
             f'appears on {n_cards} cards between {dev_win.ts.min():%Y-%m-%d} and {dev_win.ts.max():%Y-%m-%d}']
    if new_share >= .8:
        parts.append(f'{new_share:.0%} of those transactions mark the device New to the account')
    if anon_share >= .8:
        parts.append(f'{anon_share:.0%} are behind an anonymous/hidden proxy')
    if amt_cluster >= 3:
        parts.append(f'{amt_cluster} cards show near-identical amounts (~{money(f.TransactionAmt)})')
    if len(conf):
        parts.append(f'{len(conf)} confirmed-fraud closed cases already involve this profile '
                     f'({", ".join(conf.case_id.head(6))})')
    emails = dev_win.P_emaildomain.dropna()
    if len(emails) and emails.value_counts(normalize=True).iloc[0] >= .8 and emails.iloc[0] not in ('gmail.com',):
        parts.append(f'same purchaser email domain ({emails.value_counts().index[0]}) on most of them')
    return [Signal('shared_device_ring', w, '; '.join(parts) + '.', ref,
                   [card_id] + others[:15] + list(conf.case_id.head(6)),
                   episode=_ids(own), connected_cards=others, devices=[f.device_profile],
                   # proxy-masked or same-amount rings match no documented typology (cf. CC-2649..CC-3035);
                   # a ring of plain new-device purchases is pattern 3 with a shared origin (R6)
                   pattern='undocumented' if (anon_share >= .8 or amt_cluster >= 3) else 'card_not_present_new_device')]


# ---------------------------------------------------------------- repeated near-identical charges
def repeat_burst(f, win, ref):
    if f.channel != 'online':
        return []
    w = win[(win.channel == 'online') & ((win.ts - f.ts).abs() <= pd.Timedelta('2h')) &
            ((win.TransactionAmt - f.TransactionAmt).abs() <= 0.02 * f.TransactionAmt) &
            ((win.device_profile == f.device_profile) | (win.P_emaildomain == f.P_emaildomain))]
    if len(w) >= 2:
        pm = float(w.p_model.mean())
        return [Signal('repeat_charge_burst', 1.2 + (0.8 if pm >= .5 else 0),
                       f'{len(w)} near-identical online charges ({", ".join(money(a) for a in w.TransactionAmt)}) '
                       f'within {(w.ts.max() - w.ts.min()).total_seconds() / 60:.0f} minutes from the same device/email; '
                       f'case-memory model mean score {pm:.2f}', ref, _ids(w), episode=_ids(w),
                       pattern='card_not_present_fraud')]
    return []


# ---------------------------------------------------------------- device / email / product novelty
def novelty(f, st, ref):
    out = []
    if f.channel == 'online' and pd.notna(f.device_profile) and not str(f.device_profile).startswith('NA | NA | NA'):
        if f.device_profile in st['devices']:
            out.append(Signal('device_known', -0.8, f'Device profile "{f.device_profile}" was used on this card more than a week before this alert',
                              ref, [str(int(f.TransactionID))]))
        elif f.id_15 == 'New':
            out.append(Signal('new_device', 0.6, f'Device profile "{f.device_profile}" is marked New and has never been '
                              f'seen on this card ({st["online"]} prior online transactions)', ref,
                              [str(int(f.TransactionID))], devices=[f.device_profile], pattern='card_not_present_new_device'))
        if f.id_23 in ('IP_PROXY:ANONYMOUS', 'IP_PROXY:HIDDEN'):
            out.append(Signal('proxy', 0.3, f'Connection behind {f.id_23}', ref, [str(int(f.TransactionID))]))
    if st['n'] >= 10 and pd.notna(f.P_emaildomain) and f.P_emaildomain not in st['emails']:
        out.append(Signal('new_email', 0.4, f'Purchaser email domain {f.P_emaildomain} never used on this card '
                          f'in {st["n"]} prior transactions', ref, [str(int(f.TransactionID))]))
    if st['n'] >= 10 and st['products'].get(f.ProductCD, 0) <= 1:
        out.append(Signal('new_product', 0.4, f'Product code {f.ProductCD} used {st["products"].get(f.ProductCD, 0)} '
                          f'times in {st["n"]} prior transactions on this card', ref, [str(int(f.TransactionID))]))
    return out


def amount(f, st, ref):
    if st['n'] < 5:
        return []
    if f.TransactionAmt >= st['p95'] and f.TransactionAmt >= 2 * st['med']:
        return [Signal('unusual_amount', 0.7, f'{money(f.TransactionAmt)} is above the card\'s 95th percentile '
                       f'({money(st["p95"])}); median spend {money(st["med"])}', ref, [str(int(f.TransactionID))])]
    if f.TransactionAmt <= st['p90']:
        return [Signal('amount_in_range', -0.3, f'{money(f.TransactionAmt)} is within the card\'s normal range '
                       f'(median {money(st["med"])}, 90th percentile {money(st["p90"])})', ref,
                       [str(int(f.TransactionID))], independent=False)]
    return []


# ---------------------------------------------------------------- pattern 4: region
def region(f, st, win, ref):
    if f.channel != 'in_person' or pd.isna(f.addr1):
        return []
    prior = st['regions'].get(f.addr1, 0)
    if prior >= 10:
        return [Signal('region_habitual', -0.8, f'Billing region {f.addr1:g} has {prior} prior card-present '
                       f'transactions on this card', ref, [str(int(f.TransactionID))])]
    if prior <= 1:
        rw = win[(win.addr1 == f.addr1) & (win.ts >= f.ts - pd.Timedelta('7D'))]
        days = rw.ts.dt.date.nunique()
        if days >= 3:
            return [Signal('trip', -1.0, f'Region {f.addr1:g} used on {days} different days this week: '
                           f'consistent with a trip, not a clone', ref, _ids(rw))]
        home = win[(win.addr1 != f.addr1) & ((win.ts - f.ts).abs() <= pd.Timedelta('24h')) & (win.channel == 'in_person')]
        if len(home):
            ep = _ids(rw)
            return [Signal('out_of_region', 1.2, f'Card-present use in region {f.addr1:g} (no prior history) while '
                           f'{len(home)} card-present transactions continue in other regions within 24h', ref,
                           ep, episode=ep, pattern='out_of_region_use')]
    return []


# ---------------------------------------------------------------- the real cardholder's habits
def cardholder_habit(f, uh, ref):
    h = uh[uh.ts < f.ts]
    if len(h) < 5:
        return []
    med = h.TransactionAmt.median()
    same = h[(h.ProductCD == f.ProductCD) & (h.addr1 == f.addr1)]
    near = h[(h.TransactionAmt - f.TransactionAmt).abs() <= 0.05 * f.TransactionAmt]
    if len(same) >= 5 and 0.5 * med <= f.TransactionAmt <= 1.8 * med:
        extra = f'; {len(near)} earlier payments within 5% of this amount (recurring)' if len(near) >= 3 else ''
        return [Signal('cardholder_habit', -1.5 - (0.5 if len(near) >= 3 else 0),
                       f'Matches the cardholder\'s own habitual spend: {len(same)} earlier product-{f.ProductCD} '
                       f'purchases in region {f.addr1:g} since {h.ts.min():%Y-%m-%d}, median {money(med)}{extra}',
                       ref, _ids(same.tail(6)))]
    return []


def model_signal(f):
    p = float(f.p_model) if pd.notna(f.p_model) else None
    if p is None:
        return []
    return [Signal('case_memory_model', 0.0, f'Case-memory model (trained on 5,565 closed cases) scores the flagged '
                   f'transaction {p:.2f}; bank risk score {f.risk_score:.2f}', 'model:case_memory_lgbm',
                   [str(int(f.TransactionID))], source='external', independent=False)]


# ---------------------------------------------------------------- proximity to known fraud
def proximity(prox, card_id):
    """Confirmed-fraud closed cases reachable card -> txn -> rare device -> txn -> ClosedCase (2 hops)."""
    n = len(prox.get('cases', []))
    if n == 0:
        return []
    return [Signal('fraud_proximity', 0.3 if n >= 2 else 0.0,
                   f'{n} confirmed-fraud closed case(s) within two hops of this card through shared rare device '
                   f'profiles in the last 30 days ({", ".join(prox["cases"][:6])})', 'query:fraud_proximity',
                   [card_id] + prox['cases'][:6], independent=False)]
