"""Answer-file contract: policy consistency checks on cases/*.json (run after run_cases.py)."""
import glob, json
from agent.actions import required_route

FILES = sorted(glob.glob('cases/*.json'))


def test_twenty_answers():
    assert len(FILES) == 20


def test_routes_and_sar_consistency():
    for f in FILES:
        a = json.load(open(f))
        exp = a['case']['exposure_usd']
        for ph in ('initial', 'final'):
            for x in a['next_best_actions'][ph]:
                assert x['route'] == required_route(x['action'], exp if x['action'] == 'BLOCK_CARD' else 0), f
                assert x['reason'], f
        assert a['sar']['file'] == any(x['action'] == 'FILE_REPORT' for x in a['next_best_actions']['final']), f
        if a['case']['verdict'] == 'legitimate':
            assert a['case']['exposure_usd'] == 0 and not a['sar']['file'], f
        if a['evidence_requests']:
            assert a['case']['status'] != 'open' or a['next_best_actions']['what_changed'] != 'nothing', f
        else:
            assert a['next_best_actions']['initial'] == a['next_best_actions']['final'], f
