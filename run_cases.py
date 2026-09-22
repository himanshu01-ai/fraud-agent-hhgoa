"""
Run the agent on the case pack and write cases/<case_id>.json (+ traces for the dashboard).
  python run_cases.py --data-dir /path/to/HHGOA_IEEE --backend local
  python run_cases.py --data-dir ... --backend tigergraph        # GSQL via pyTigerGraph, cases written to graph
  python run_cases.py --data-dir ... --backend mcp --llm         # GSQL via TigerGraph MCP server + LLM narratives
"""
import argparse, glob, json, os
import pandas as pd
from agent.backends import LocalBackend, TigerGraphBackend
from agent.retrieval import Retriever
from agent.investigator import Investigator


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-dir', required=True)
    ap.add_argument('--backend', default='local', choices=['local', 'tigergraph', 'mcp'])
    ap.add_argument('--llm', action='store_true')
    ap.add_argument('--cases', default='all')
    a = ap.parse_args()
    cc_path = glob.glob(os.path.join(a.data_dir, '*closed_cases_history.csv'))[0]
    cp = pd.read_csv(glob.glob(os.path.join(a.data_dir, '*case_pack.csv'))[0])
    if a.cases != 'all':
        cp = cp[cp.case_id.isin(a.cases.split(','))]
    g = LocalBackend(cc_path=cc_path) if a.backend == 'local' else TigerGraphBackend(cc_path=cc_path, use_mcp=a.backend == 'mcp')
    agent = Investigator(g, Retriever(pd.read_csv(cc_path)), use_llm=a.llm)
    os.makedirs('cases', exist_ok=True); os.makedirs('ui/traces', exist_ok=True)
    rows = []
    for case in cp.sort_values('opened_at').to_dict('records'):   # chronological: memory builds up
        ans, trace = agent.run(case)
        json.dump(ans, open(f'cases/{case["case_id"]}.json', 'w'), indent=2)
        json.dump(trace, open(f'ui/traces/{case["case_id"]}.json', 'w'), indent=1, default=str)
        c = ans['case']
        rows.append([case['case_id'], case['trigger_type'], c['verdict'], c['fraud_probability'], c['pattern'],
                     c['exposure_usd'], ans['sar']['file'],
                     '/'.join(x['action'] for x in ans['next_best_actions']['final'])])
    print(pd.DataFrame(rows, columns=['case', 'trigger', 'verdict', 'p', 'pattern', 'exposure', 'sar', 'final'])
          .sort_values('case').to_string(index=False))


if __name__ == '__main__':
    main()
