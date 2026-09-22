"""
Explanations.  Deterministic templates always produce a complete summary + SAR narrative from
graph facts.  If ANTHROPIC_API_KEY is set (and --llm is used) the LLM rewrites them for clarity
using ONLY the GraphRAG context (facts, evidence claims, cited policy rules, similar case notes);
it may not add facts, change the verdict, the actions or any number.
"""
import json, os


def money(x):
    return f'${x:,.2f}'


def template_summary(ctx):
    v, pat = ctx['verdict'], ctx['pattern']
    lead = {'fraud': f'Fraud ({pat.replace("_", " ")})', 'legitimate': 'Legitimate activity',
            'uncertain': 'Unresolved alert'}[v]
    trig = ctx['trigger_text'].split(' Review')[0]
    s = [f'{lead} on card {ctx["card_id"]} ({ctx["trigger_type"].replace("_", " ")}): {trig}']
    top = [e['claim'] for e in ctx['evidence'] if e['source'] in ('graph', 'external')][:2]
    s += top
    if ctx['response']:
        s.append(f'Evidence requested; assumed response: {ctx["assumed_response"].split(" (simulated")[0]}.')
    s.append(f'Final probability {ctx["p_final"]:.2f}; exposure {money(ctx["exposure"])}; actions: '
             f'{", ".join(a["action"] for a in ctx["final"])}.')
    return ' '.join(x.rstrip('.') + '.' for x in s)[:1400]


def template_sar(ctx):
    ep = ctx['episode_rows']
    if not ep:
        return ''
    first, last = ep[0]['ts'], ep[-1]['ts']
    lines = ', '.join(f'{r["id"]} ({money(r["amt"])} {r["channel"]}, {r["ts"][:16]}'
                      + (f', device "{r["device"]}"' if r['device'] else '')
                      + (f', region {r["addr1"]}' if r['addr1'] else '') + ')' for r in ep[:8])
    s = [f'Subject: customer {ctx["customer_id"]}, card {ctx["card_id"]}.',
         f'Between {first[:16]} and {last[:16]}, {len(ep)} transaction(s) totalling {money(ctx["exposure"])} were '
         f'identified as unauthorised: {lines}.',
         f'The alert was raised by {ctx["trigger_type"].replace("_", " ")}: {ctx["trigger_text"]}']
    if ctx['pattern'] == 'undocumented':
        s.append(f'Method: {ctx["pattern_description"]}')
    for e in [e for e in ctx['evidence'] if e['source'] == 'graph' and e.get('_fraud')][:3]:
        s.append(e['claim'])
    if ctx['connected_cards']:
        s.append(f'The same origin links the activity to {len(ctx["connected_cards"])} other card(s), including '
                 f'{", ".join(ctx["connected_cards"][:8])}, indicating a common actor across cardholders.')
    if ctx['similar']:
        s.append(f'The method matches previously confirmed bank cases {", ".join(ctx["similar"][:5])}.')
    if ctx['response'] == 'deny' or ctx['trigger_type'] == 'customer_report':
        s.append('The cardholder stated they did not authorise the transaction(s) and retains the card.')
    s.append('Why suspicious: the activity is inconsistent with the cardholder\'s established behaviour and matches '
             'a fraud typology corroborated by independent graph evidence. Actions: '
             + ', '.join(a['action'] for a in ctx['final']) + '.')
    return ' '.join(x.rstrip('.') + '.' for x in s)


def llm_rewrite(ctx, summary, sar):
    key = os.environ.get('ANTHROPIC_API_KEY')
    if not key:
        return summary, sar, 0
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    facts = {k: ctx[k] for k in ['case_id', 'card_id', 'customer_id', 'trigger_text', 'verdict', 'pattern',
                                 'pattern_description', 'p_initial', 'p_final', 'exposure', 'connected_cards',
                                 'similar', 'assumed_response']}
    facts['evidence'] = [e['claim'] for e in ctx['evidence']]
    facts['initial_actions'] = ctx['initial']
    facts['final_actions'] = ctx['final']
    facts['policy_rules'] = ctx['rule_texts']
    facts['similar_case_notes'] = ctx['similar_notes']
    prompt = ('You are a bank fraud investigator writing the case record. Using ONLY the facts below, rewrite '
              '(1) "summary": 2-6 sentences for an analyst, and (2) "sar": the suspicious activity report narrative '
              '(6-12 sentences: who, what, when, where, how, why suspicious) or "" if the draft SAR is empty. '
              'Do not invent IDs, amounts, dates or facts; do not change the verdict or actions. '
              'Return JSON {"summary":..., "sar":...} only.\n\nFACTS:\n' + json.dumps(facts, default=str)
              + '\n\nDRAFT SUMMARY:\n' + summary + '\n\nDRAFT SAR:\n' + sar)
    try:
        r = client.messages.create(model=os.environ.get('LLM_MODEL', 'claude-sonnet-4-6'), max_tokens=1500,
                                   messages=[{'role': 'user', 'content': prompt}])
        txt = ''.join(b.text for b in r.content if b.type == 'text').strip().strip('`')
        txt = txt[txt.index('{'):txt.rindex('}') + 1]
        out = json.loads(txt)
        tokens = r.usage.input_tokens + r.usage.output_tokens
        return out.get('summary') or summary, (out.get('sar') if sar else ''), tokens
    except Exception as e:
        print('LLM rewrite skipped:', e)
        return summary, sar, 0
