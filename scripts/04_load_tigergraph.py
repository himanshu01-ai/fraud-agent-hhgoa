"""
Step 4 - Create schema, load data, install queries on TigerGraph Savanna / Community Edition.
Requires .env (see .env.example).  Run steps selectively with --steps schema,load,queries
Usage: python scripts/04_load_tigergraph.py --steps schema,load,queries
"""
import argparse, glob, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent.tg_conn import connect


def run_gsql(conn, path):
    txt = open(path).read()
    print(f'--- {path}')
    print(conn.gsql(txt))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--steps', default='schema,load,queries')
    a = ap.parse_args()
    steps = a.steps.split(',')
    conn = connect()

    if 'schema' in steps:
        run_gsql(conn, 'graph/schema.gsql')
        run_gsql(conn, 'graph/loading_job.gsql')

    if 'load' in steps:
        for f in sorted(glob.glob('data/graph/txn_*.csv')):
            t = time.time()
            r = conn.runLoadingJobWithFile(f, 'f_txn', 'load_txn', sep=',', eol='\n')
            print(f, 'loaded in %.1fs' % (time.time() - t), str(r)[:200])
        for f, tag in [('data/graph/closed_cases.csv', 'f_cc'), ('data/graph/cc_txn.csv', 'f_cc_txn'),
                       ('data/graph/cc_conn.csv', 'f_cc_conn')]:
            r = conn.runLoadingJobWithFile(f, tag, 'load_cases', sep=',', eol='\n')
            print(f, str(r)[:200])
        print('vertex counts:', conn.getVertexCount('*'))

    if 'queries' in steps:
        run_gsql(conn, 'graph/queries.gsql')


if __name__ == '__main__':
    main()
