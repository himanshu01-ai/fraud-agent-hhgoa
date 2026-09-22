"""
The investigation agent.  Follows the challenge's flow and records every step:
 1 Trigger   2 Investigate (open context)   3 Gather evidence (GSQL tools)   4 Assess uncertainty
 5 Gather more evidence if needed (policy-approved, simulated reply)   6 Next actions (before/after)
 7 Explain   8 Update case memory (write InvestigationCase to TigerGraph)
"""
import time
import pandas as pd
from agent import detectors as D
from agent.policy import assess, decide, sar_required, verdict_of
from agent.narrative import template_summary, template_sar, llm_rewrite
from agent.actions import ActionExecutor

START = pd.Timestamp('2016-07-01')


class Investigator:
    def __init__(self, backend, retriever, use_llm=False):
        self.g, self.r, self.use_llm = backend, retriever, use_llm

    def run(self, case, force_response=None):
        t0, g = time.time(), self.g
        g.reset_log()
        trace = []
        step = lambda name, detail: trace.append({'step': len(trace) + 1, 'name': name, 'detail': detail,
                                                   'tool_calls_so_far': len(g.calls)})
        asof = pd.Timestamp(case['opened_at'])
        card = case['card_id']
        # 1 trigger
        f = g.get_txn(case['flagged_txn_id'])
        step('trigger', f'{case["trigger_type"]}: {case["trigger_text"]}')
        # 2-3 gather evidence from the graph (as of the case opening time: no look-ahead)
        hist = g.card_txns(card, START, f.ts - pd.Timedelta('1s'))
        win = g.card_txns(card, f.ts - pd.Timedelta('7D'), asof)
        st = D.card_stats(hist, f.ts)
        step('card_profile', f'{st["n"]} prior transactions on {card}; median ${st["med"]:.2f}' if st['n'] else 'no history')
        uh = g.cardholder_txns(f.uid) if isinstance(f.uid, str) else hist.iloc[0:0]
        uh = uh[uh.ts <= asof]
        step('cardholder_profile', f'behaviour profile {f.uid}: {len(uh)} transactions')
        dev_win, fp, dev_cases = win.iloc[0:0], {}, pd.DataFrame(columns=['case_id', 'outcome'])
        generic = not isinstance(f.device_profile, str) or f.device_profile.startswith('NA | NA')
        if not generic:
            fp = g.device_footprint(f.device_profile)
            if fp.get('n_customers', 999) <= 200:
                dev_win = g.device_txns(f.device_profile, f.ts - pd.Timedelta('14D'), asof)
                dev_cases = g.cases_by_device(f.device_profile)
            step('device_neighbourhood', f'profile used by {fp.get("n_customers")} customers overall; '
                 f'{dev_win.card_id.nunique() if len(dev_win) else 0} cards in the 14-day window')
        prox = g.fraud_proximity(card, f.ts - pd.Timedelta('30D'), asof)
        card_cases = g.cases_by_card(card)
        step('prior_cases', f'{len(card_cases)} closed cases on this card, {len(dev_cases)} on this device')

        ref = f'query:card_txns(c={card})'
        dref = f'query:device_txns(d="{f.device_profile}")'
        sig = []
        sig += D.structuring(f, win, ref)
        sig += D.card_testing(f, win, ref)
        sig += D.device_ring(f, dev_win, fp, dev_cases, card, dref, 'query:cases_by_device')
        sig += D.repeat_burst(f, win, ref)
        sig += D.novelty(f, st, ref)
        sig += D.amount(f, st, ref)
        sig += D.region(f, st, win, ref)
        sig += D.cardholder_habit(f, uh, f'query:cardholder_txns(h={f.uid})')
        sig += D.proximity(prox, card)
        sig += D.model_signal(f)
        step('detectors', ', '.join(f'{s.name}({s.weight:+.1f})' for s in sig))

        # 4 assess
        a = assess(sig, f, case['trigger_type'])
        undocumented = a['pattern'] == 'undocumented'
        connected = sorted({c for s in sig for c in s.connected_cards})
        episode = sorted({t for s in sig if s.weight > 0 for t in s.episode} | {str(int(f.TransactionID))}, key=int)
        ep_rows = win[win.TransactionID.astype(str).isin(episode)]
        if len(ep_rows) < len(episode):
            ep_rows = pd.concat([ep_rows, dev_win[dev_win.TransactionID.astype(str).isin(episode)]]).drop_duplicates('TransactionID')
        ep_rows = ep_rows.sort_values('ts')
        exposure = round(float(ep_rows.TransactionAmt.abs().sum()), 2)
        has_conn = bool(connected)
        step('assess', f'p={a["p"]:.2f}, {a["fraud_ev"]} fraud / {a["legit_ev"]} legitimate independent evidence, '
             f'provisional pattern {a["pattern"]}, verdict {verdict_of(a["p"])}')

        # 5-6 policy: initial actions, evidence requests, simulated reply, final actions
        plan = decide(a, sig, f, case['trigger_type'], exposure, has_conn, undocumented, force_response)
        for rq in plan['requests']:
            rq['asked_after_step'] = len(trace)
        history = [{'phase': 'assessment', 'probability': a['p'], 'verdict': verdict_of(a['p']),
                    'recommended': [x['action'] for x in plan['initial']]}]
        for rq in plan['requests']:
            history.append({'phase': 'evidence_request', 'type': rq['type'], 'response': plan['response'],
                            'detail': rq['assumed_response']})
        if plan['requests']:
            history.append({'phase': 'reassessment', 'probability': plan['p_final'], 'verdict': plan['verdict'],
                            'recommended': [x['action'] for x in plan['final']]})
        step('policy', f'initial={[x["action"] for x in plan["initial"]]} response={plan["response"]} '
             f'final={[x["action"] for x in plan["final"]]}')
        verdict = plan['verdict']
        pattern = a['pattern'] if verdict == 'fraud' else ('none' if verdict == 'legitimate' else a['pattern'])
        if verdict == 'legitimate':
            episode, exposure, connected, ep_rows = [], 0.0, [], ep_rows.iloc[0:0]
        sar = sar_required(verdict, exposure, has_conn, undocumented)
        if sar and not any(x['action'] == 'FILE_REPORT' for x in plan['final']):
            plan['final'].append({'action': 'FILE_REPORT', 'route': 'L2', 'reason': '§3a report criteria met'})

        # GraphRAG memory retrieval
        names = {s.name for s in sig}
        query = ' '.join(s.claim for s in sig if s.weight != 0)
        similar = []
        similar += list(dev_cases[dev_cases.outcome == 'confirmed_fraud'].case_id.head(4)) if not generic else []
        if verdict == 'legitimate':
            q = ('new phone device' if 'new_device' in names else 'travel billing region' if f.channel == 'in_person'
                 else 'amount unusual stated intent')
            similar += self.r.typology(q, 'none', float(f.TransactionAmt), k=2, cleared=True)
        else:
            similar += self.r.typology(query, pattern if pattern != 'none' else a['pattern'], exposure or float(f.TransactionAmt), k=3)
        similar += list(card_cases.sort_values('opened_at').case_id.tail(1))
        similar = list(dict.fromkeys(similar))[:6]
        mem = g.case_memory(pattern, None if generic else f.device_profile)
        mem = [m for m in mem if (not generic and f.device_profile in m.get('devices', [])) or
               (m.get('pattern') == pattern and pattern not in ('undocumented', 'none'))]
        step('memory', f'retrieved closed cases {similar}; {len(mem)} earlier investigations in case memory')

        # evidence list
        fraud_names = {s.name for s in sig if s.weight > 0}
        evidence = []
        for s in sig:
            evidence.append({'claim': s.claim, 'source': s.source, 'ref': s.ref, 'entity_ids': s.entity_ids,
                             '_fraud': s.name in fraud_names})
        if len(card_cases):
            cf = card_cases[card_cases.outcome == 'confirmed_fraud']
            evidence.append({'claim': f'{len(card_cases)} earlier closed case(s) on this card ({len(cf)} confirmed fraud)',
                             'source': 'graph', 'ref': 'query:cases_by_card', 'entity_ids': list(card_cases.case_id.tail(5))})
        if mem:
            evidence.append({'claim': f'Case memory: {len(mem)} earlier investigation(s) with the same pattern/device '
                             f'({", ".join(m.get("graph_case_id", m.get("case_id", "")) for m in mem[-3:])})',
                             'source': 'graph', 'ref': 'query:case_memory', 'entity_ids': []})
        for rq in plan['requests']:
            evidence.append({'claim': rq['assumed_response'].split(' (simulated')[0], 'source': 'customer',
                             'ref': 'evidence_request:1', 'entity_ids': []})
        rules = sorted({w for x in plan['initial'] + plan['final'] for w in
                        __import__('re').findall(r'R\d+', x['reason'])}, key=lambda r: int(r[1:]))
        for rl in rules:
            evidence.append({'claim': f'Policy {rl} applied', 'source': 'document',
                             'ref': f'rag/fraud_policy.md#{rl}', 'entity_ids': []})

        desc = ''
        if pattern == 'undocumented':
            if 'structuring_under_500' in names:
                desc = ('Threshold structuring: several online purchases within minutes, each priced just under a $500 '
                        'authorization limit, from devices new to the account, so no single purchase trips a '
                        'large-amount rule. Found by scanning the card for clustered sub-$500 online purchases; '
                        'the same shape appears in five confirmed closed cases in September.')
            else:
                desc = ('Shared-device ring: one rare device profile (' + str(f.device_profile) + ') makes online '
                        'purchases on many unrelated cards in a short window, typically New to each account and '
                        'behind a proxy. Found with the two-hop card→device→card traversal; it affects every '
                        'cardholder whose card the ring holds.')
        ep_list = [{'id': str(int(r.TransactionID)), 'amt': float(r.TransactionAmt), 'channel': r.channel,
                    'ts': str(r.ts), 'device': r.device_profile if isinstance(r.device_profile, str) else '',
                    'addr1': f'{r.addr1:g}' if r.addr1 == r.addr1 else ''} for r in ep_rows.itertuples()]
        devices = sorted({d for s in sig for d in s.devices}) if verdict != 'legitimate' else []
        if pattern not in ('undocumented', 'card_not_present_new_device') and not connected:
            devices = []
        ctx = dict(case_id=case['case_id'], card_id=card, customer_id=case['customer_id'],
                   trigger_type=case['trigger_type'], trigger_text=case['trigger_text'], verdict=verdict,
                   pattern=pattern, pattern_description=desc, p_initial=a['p'], p_final=plan['p_final'],
                   exposure=exposure, connected_cards=connected, similar=similar, evidence=evidence,
                   initial=plan['initial'], final=plan['final'], response=plan['response'],
                   assumed_response=plan['requests'][0]['assumed_response'] if plan['requests'] else '',
                   episode_rows=ep_list, rule_texts={r_: self.r.rule_text(r_) for r_ in rules},
                   similar_notes=self.r.notes_for(similar))
        summary, sar_text, tokens = template_summary(ctx), (template_sar(ctx) if sar else ''), 0
        if self.use_llm:
            summary, sar_text, tokens = llm_rewrite(ctx, summary, sar_text)
        step('explain', 'summary and report narrative written' + (' (LLM, grounded)' if tokens else ' (template)'))

        # 8 case memory
        gid = f'INV-{case["case_id"]}'
        rec = dict(graph_case_id=gid, case_id=case['case_id'], card_id=card, opened_at=case['opened_at'],
                   trigger_type=case['trigger_type'], status=plan['status'], verdict=verdict,
                   fraud_probability=plan['p_final'], pattern=pattern, pattern_description=desc,
                   exposure_usd=exposure, sar_filed=sar, final_actions=[x['action'] for x in plan['final']],
                   summary=summary, affected_txn_ids=episode if verdict != 'legitimate' else [],
                   connected_card_ids=connected, devices=devices, similar_prior_cases=similar)
        answer = {
            'case_id': case['case_id'],
            'case': {'status': plan['status'], 'verdict': verdict, 'fraud_probability': plan['p_final'],
                     'pattern': pattern, 'pattern_description': desc,
                     'affected_txn_ids': rec['affected_txn_ids'],
                     'first_suspicious_txn_id': rec['affected_txn_ids'][0] if rec['affected_txn_ids'] else '',
                     'connected_card_ids': connected, 'connected_device_profiles': devices,
                     'exposure_usd': exposure,
                     'evidence': [{k: v for k, v in e.items() if not k.startswith('_')} for e in evidence],
                     'similar_prior_cases': similar, 'summary': summary,
                     'written_to_graph': False, 'graph_case_id': gid},
            'evidence_requests': [{'type': rq['type'], 'asked_after_step': rq['asked_after_step'],
                                   'assumed_response': rq['assumed_response']} for rq in plan['requests']],
            'next_best_actions': {'initial': plan['initial'], 'final': plan['final'],
                                  'what_changed': what_changed(plan, a)},
            'sar': ({'file': True, 'reason': sar_reason(exposure, has_conn, undocumented), 'narrative': sar_text,
                     'subjects': [case['customer_id'], card] + connected[:10] + devices[:2],
                     'total_amount_usd': exposure,
                     'activity_dates': [ep_list[0]['ts'][:10], ep_list[-1]['ts'][:10]] if ep_list else []}
                    if sar else {'file': False, 'reason': no_sar_reason(verdict, exposure), 'narrative': '',
                                 'subjects': [], 'total_amount_usd': 0, 'activity_dates': []}),
            'stop_reason': plan['stop'],
            'tool_calls': 0, 'tokens': tokens, 'latency_s': 0,
        }
        # execute within code-enforced permissions: auto actions run, L1/L2 wait for a human
        execu = ActionExecutor(history)
        if plan['requests']:            # actions taken before the reply came back
            for x in plan['initial']:
                execu.execute(x['action'], exposure, card)
        for x in plan['final']:
            execu.execute(x['action'], exposure, card)
        step('execute', ', '.join(f'{h["action"]}:{h["status"]}' for h in history if 'status' in h))
        rec['decision_history'] = history
        written = g.write_case(rec, answer)
        answer['case']['written_to_graph'] = bool(written)
        answer['tool_calls'] = len(g.calls)
        answer['latency_s'] = round(time.time() - t0, 2)
        step('case_memory_write', f'{gid} written to {"TigerGraph" if written else "local case memory"}')
        return answer, {'case_id': case['case_id'], 'trace': trace, 'tool_log': g.calls, 'decision_history': history,
                        'p_initial': a['p'], 'episode': ep_list, 'flagged': {
                            'id': str(int(f.TransactionID)), 'amt': float(f.TransactionAmt), 'ts': str(f.ts),
                            'channel': f.channel, 'device': f.device_profile if isinstance(f.device_profile, str) else '',
                            'region': f'{f.addr1:g}' if f.addr1 == f.addr1 else '', 'risk_score': round(float(f.risk_score), 2),
                            'p_model': float(f.p_model) if f.p_model == f.p_model else None}}


def what_changed(plan, a):
    if not plan['requests']:
        return 'nothing'
    r = plan['response']
    msg = {'confirm': 'Customer confirmed the transaction', 'deny': 'Customer denied the transaction',
           'noreply': 'No customer reply within 24 hours'}[r]
    return (f'{msg}: probability moved from {a["p"]:.2f} to {plan["p_final"]:.2f} and the recommendation changed '
            f'from {", ".join(x["action"] for x in plan["initial"])} to {", ".join(x["action"] for x in plan["final"])}.')


def sar_reason(exposure, conn, undoc):
    why = []
    if exposure > 1000:
        why.append(f'exposure ${exposure:,.2f} exceeds $1,000')
    if conn:
        why.append('activity connects to a shared device profile and other cardholders (R6)')
    if undoc:
        why.append('coordinated / undocumented pattern (R9)')
    return 'File under §3a: fraud confirmed/strongly suspected and ' + '; '.join(why) + '.'


def no_sar_reason(verdict, exposure):
    if verdict != 'fraud':
        return f'No report: verdict is {verdict}; §3a requires confirmed or strongly suspected fraud.'
    return (f'Case only, no report (§3a): exposure ${exposure:,.2f} ≤ $1,000, no shared device/region link to other '
            f'customers, known pattern.')
