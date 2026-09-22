"""
Risk assessment (evidence -> calibrated probability) and the Fraud Policy v1.0 engine
(probability + evidence -> ordered actions with approval routes, evidence requests, SAR decision).
The LLM never decides actions: this module is deterministic and cites a rule for every action.
"""
import math

from agent.actions import required_route

MAX_EVIDENCE_ROUNDS = 2   # hard cap on the evidence loop
PATTERN_PRIORITY = ['undocumented', 'card_testing', 'out_of_region_use', 'card_not_present_new_device',
                    'card_not_present_fraud', 'account_takeover']


def route(action, exposure):
    return required_route(action, exposure)


def act(action, exposure, reason):
    return {'action': action, 'route': route(action, exposure), 'reason': reason}


def sigmoid(x):
    return 1 / (1 + math.exp(-x))


def logit(p):
    p = min(max(p, 0.02), 0.98)
    return math.log(p / (1 - p))


# ------------------------------------------------------------------------------------------ assess
def assess(signals, f, trigger_type):
    base = logit(float(f.p_model)) * 0.7 if f.p_model == f.p_model else logit(0.2)
    score = base + sum(s.weight for s in signals) - 0.4
    if trigger_type == 'customer_report':
        # case memory: every customer-reported dispute in the 5,565 closed cases was confirmed fraud;
        # all 900 cleared cases were model-score alerts.  A dispute is therefore strong evidence.
        score += 2.0
    p = round(sigmoid(score), 2)
    fraud_ev = [s for s in signals if s.weight > 0 and s.independent]
    legit_ev = [s for s in signals if s.weight < 0 and s.independent]
    if f.p_model == f.p_model:
        if f.p_model >= 0.5:
            fraud_ev.append('model')
        if f.p_model <= 0.05:
            legit_ev.append('model')
    if trigger_type == 'customer_report':
        fraud_ev.append('customer_denial')
    pats = {s.pattern for s in signals if s.weight > 0 and s.pattern}
    pattern = next((p_ for p_ in PATTERN_PRIORITY if p_ in pats), None)
    if pattern is None:
        names = {s.name for s in signals}
        if f.channel == 'online':
            pattern = 'card_not_present_fraud'
        elif 'new_email' in names:
            pattern = 'account_takeover'
        else:
            pattern = 'out_of_region_use' if 'out_of_region' in names else 'card_not_present_fraud'
    return dict(p=p, fraud_ev=len(fraud_ev), legit_ev=len(legit_ev), pattern=pattern)


def verdict_of(p):
    return 'fraud' if p >= 0.70 else ('legitimate' if p <= 0.30 else 'uncertain')


# ------------------------------------------------------------------------------------------ policy
def decide(a, signals, f, trigger_type, episode_amt, has_connected, undocumented, force_response=None):
    """Returns plan dict: initial, final, evidence_requests, p_final, response, stop_reason, rules."""
    p, names = a['p'], {s.name for s in signals}
    exposure0 = float(f.TransactionAmt)
    habit = bool({'cardholder_habit'} & names)
    testing = 'card_testing_sequence' in names
    plan = {'requests': [], 'response': None}

    strong_fraud = p >= 0.85 and a['fraud_ev'] >= 2
    strong_legit = p <= 0.15 and a['legit_ev'] >= 2 and trigger_type != 'customer_report'
    denial_settled = trigger_type == 'customer_report' and p >= 0.5

    if strong_legit:
        acts = [act('CLOSE_NO_FRAUD', 0, f'§6 stopping: probability {p:.2f} with {a["legit_ev"]} independent '
                    f'pieces of legitimate evidence; no rule calls for verification')]
        plan.update(initial=acts, final=acts, p_final=p, verdict='legitimate', status='closed_legitimate',
                    stop=f'Probability {p:.2f} ≤ 0.15 supported by {a["legit_ev"]} independent pieces of evidence '
                         f'(§6). Further steps would not change the decision.')
        return plan

    if strong_fraud or denial_settled:
        final = fraud_actions(episode_amt, has_connected, undocumented, testing, trigger_type)
        pf = max(p, 0.85) if denial_settled else p
        plan.update(initial=final, final=final, p_final=round(min(pf, 0.99), 2), verdict='fraud', status='closed_fraud',
                    stop=('Customer denial plus corroborating graph evidence settles the verdict (R2, §6); '
                          if denial_settled else f'Probability {p:.2f} ≥ 0.85 with {a["fraud_ev"]} independent '
                          f'pieces of evidence (§6); ') + 'episode, connected cards and report decision complete.')
        return plan

    # ---------- uncertain: gather more evidence (R1 / 3a) ----------
    initial = [act('CREATE_CASE', exposure0, '§3a: evidence is being requested / customer dispute — open a case')]
    if trigger_type == 'customer_report' and habit:
        initial += [act('VERIFY_WITH_CUSTOMER', exposure0, 'R7: disputed charge matches the cardholder\'s own '
                        'recurring pattern — confirm details with the customer, do not block'),
                    act('WARN_CUSTOMER', exposure0, 'R7: remind the customer of the recurring charge')]
    else:
        initial.append(act('VERIFY_WITH_CUSTOMER', exposure0, f'R1: assessed probability {p:.2f} < 0.70 on weak / '
                           f'single-signal evidence — verify before any block'))
        if f.channel == 'online' and p >= 0.40:
            initial.append(act('STEP_UP_AUTH', exposure0, 'R1: hold further online activity behind a one-time '
                               'passcode while verification is pending'))
    plan['initial'] = initial
    plan['requests'].append({'type': 'customer_validation', 'asked_after_step': 6})

    # simulated response — deterministic function of the evidence, stated in the case file
    if trigger_type == 'customer_report':
        if p < 0.30:
            resp = ('confirm', 'Shown the merchant, date, amount and region, the customer recognises the charge as '
                    'their own (it matches their regular spending) and withdraws the dispute')
        else:
            resp = ('deny', 'Customer re-confirms they did not make the purchase and still holds the physical card')
    else:
        if p < 0.40:
            why = ('from a new phone/computer' if 'new_device' in names else
                   'as a larger planned purchase' if 'unusual_amount' in names else 'while travelling' if
                   f.channel == 'in_person' else 'themselves')
            resp = ('confirm', f'Customer confirms they made the purchase {why}')
        elif p < 0.60:
            resp = ('noreply', 'No reply from the customer within 24 hours')
        else:
            resp = ('deny', 'Customer states they did not make the purchase and still holds the card')
    if force_response:   # demo / what-if: inject a real reply instead of the simulated one
        txt = {'confirm': 'Customer confirms they made the purchase', 'deny': 'Customer states they did not make '
               'the purchase and still holds the card', 'noreply': 'No reply from the customer within 24 hours'}
        resp = (force_response, txt[force_response] + ' [injected response]')
    plan['response'] = resp[0]
    plan['requests'][0]['assumed_response'] = resp[1] + ('' if force_response else
                                                         ' (simulated: response chosen to be consistent with the '
                                                         f'pre-request evidence, assessed probability {p:.2f})')

    if resp[0] == 'confirm':
        final = ([act('WARN_CUSTOMER', 0, 'R7: send a recurring-charge reminder; do not block')] if habit and
                 trigger_type == 'customer_report' else [])
        final.append(act('CLOSE_NO_FRAUD', 0, 'R3: customer confirmed the transaction; confirmation noted in the case'))
        plan.update(final=final, p_final=0.08, verdict='legitimate', status='closed_legitimate',
                    stop='The verification response settles the question (§6).')
    elif resp[0] == 'deny':
        final = fraud_actions(episode_amt, has_connected, undocumented, testing, 'customer_report')
        plan.update(final=final, p_final=round(min(max(p + 0.35, 0.86), 0.95), 2), verdict='fraud',
                    status='closed_fraud', stop='Customer denial settles the verdict (R2, §6).')
    else:
        final = [act('MONITOR_CARD', episode_amt, 'R4: no reply within 24h — raise monitoring for 72h'),
                 act('DECLINE_TRANSACTION', episode_amt, 'R4: decline pending authorizations while unresolved')]
        esc = episode_amt > 500
        if esc:
            final.append(act('ESCALATE_TO_ANALYST', episode_amt, f'R4/R8: verdict uncertain and exposure '
                             f'${episode_amt:,.2f} > $500'))
        plan.update(final=final, p_final=p, verdict='uncertain', status='escalated' if esc else 'open',
                    stop='Customer did not reply within 24h; further automated steps cannot resolve the conflict, '
                         + ('handed to an analyst (R8).' if esc else 'card monitored for 72h pending reply.'))
    return plan


def fraud_actions(exposure, has_connected, undocumented, testing, trigger_type):
    out = []
    if testing:
        out += [act('DECLINE_TRANSACTION', exposure, 'R5: card-testing sequence — decline pending authorization'),
                act('STEP_UP_AUTH', exposure, 'R5: require one-time passcode for further activity')]
        if exposure - 0 > 100:
            out.append(act('BLOCK_CARD', exposure, f'R5: a purchase over $100 has already cleared; exposure '
                           f'${exposure:,.2f} ({"≤" if exposure <= 2500 else ">"} $2,500)'))
    else:
        why = 'R2: customer denies the transaction' if trigger_type == 'customer_report' else \
            'Fraud confirmed by graph evidence (§6 stopping threshold met)'
        out.append(act('BLOCK_CARD', exposure, f'{why}; exposure ${exposure:,.2f} '
                       f'({"≤" if exposure <= 2500 else ">"} $2,500)'))
    out.append(act('CREATE_CASE', exposure, ('R2 / ' if trigger_type == 'customer_report' else '') + '§3a: record the investigation and write it to the graph'))
    if exposure > 1000 or has_connected or undocumented:
        why = []
        if exposure > 1000:
            why.append(f'exposure ${exposure:,.2f} > $1,000')
        if has_connected:
            why.append('activity connects to a shared device profile / other cards (R6)')
        if undocumented:
            why.append('coordinated / undocumented pattern (R9)')
        out.append(act('FILE_REPORT', exposure, '§3a: ' + '; '.join(why)))
    if has_connected:
        out.append(act('MONITOR_CONNECTED_CARDS', exposure, 'R6: monitor every card sharing the device profile'))
    if undocumented:
        out.append(act('ESCALATE_TO_ANALYST', exposure, 'R9: undocumented pattern — hand to an analyst with evidence'))
    return out


def sar_required(verdict, exposure, has_connected, undocumented):
    return verdict == 'fraud' and (exposure > 1000 or has_connected or undocumented)
