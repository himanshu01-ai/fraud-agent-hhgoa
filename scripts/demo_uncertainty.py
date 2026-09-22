"""
Prove that the next best action changes as evidence arrives (the 25% "next best action" criterion).
Runs one case three times: with the simulated reply, then with injected 'confirm', 'deny' and 'noreply'.
  python scripts/demo_uncertainty.py --data-dir $DATA --case HHG-002
"""
import argparse, glob, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from agent.backends import LocalBackend, TigerGraphBackend
from agent.retrieval import Retriever
from agent.investigator import Investigator

ap = argparse.ArgumentParser()
ap.add_argument('--data-dir', required=True)
ap.add_argument('--case', default='HHG-002')
ap.add_argument('--backend', default='local', choices=['local', 'tigergraph', 'mcp'])
a = ap.parse_args()
cc_path = glob.glob(os.path.join(a.data_dir, '*closed_cases_history.csv'))[0]
cp = pd.read_csv(glob.glob(os.path.join(a.data_dir, '*case_pack.csv'))[0])
case = cp[cp.case_id == a.case].iloc[0].to_dict()
g = LocalBackend(cc_path=cc_path, memory='data/demo_memory.json') if a.backend == 'local' else \
    TigerGraphBackend(cc_path=cc_path, use_mcp=a.backend == 'mcp')
agent = Investigator(g, Retriever(pd.read_csv(cc_path)))
print(f'\n{a.case}: {case["trigger_text"]}\n')
for resp in [None, 'confirm', 'deny', 'noreply']:
    ans, tr = agent.run(case, force_response=resp)
    nba = ans['next_best_actions']
    print(f'--- reply: {resp or "simulated"} ---')
    print('  p initial :', tr['p_initial'], '-> final', ans['case']['fraud_probability'], '|', ans['case']['verdict'],
          '|', ans['case']['status'])
    print('  initial   :', [f'{x["action"]}({x["route"]})' for x in nba['initial']])
    if ans['evidence_requests']:
        print('  reply     :', ans['evidence_requests'][0]['assumed_response'][:110])
    print('  final     :', [f'{x["action"]}({x["route"]})' for x in nba['final']])
    print('  executed  :', [f'{h["action"]}:{h["status"]}' for h in tr['decision_history'] if 'status' in h])
