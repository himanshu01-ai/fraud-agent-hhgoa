"""Adversarial permission tests: restricted actions can never execute without the right human approval."""
import pytest
from agent.actions import ActionExecutor, Approval, PermissionDenied, required_route


def test_routes_match_policy():
    assert required_route('CREATE_CASE', 0) == 'auto'
    assert required_route('DECLINE_TRANSACTION', 10) == 'L1'
    assert required_route('BLOCK_CARD', 2500) == 'L1'
    assert required_route('BLOCK_CARD', 2500.01) == 'L2'
    assert required_route('BLOCK_ALL_CARDS', 1) == 'L2'
    assert required_route('FILE_REPORT', 1) == 'L2'


def test_agent_cannot_block_alone():
    h = []
    r = ActionExecutor(h).execute('BLOCK_CARD', 100, 'C1-K1')
    assert r['status'] == 'pending_approval' and h[-1]['status'] == 'pending_approval'


def test_team_lead_cannot_file_report():
    with pytest.raises(PermissionDenied):
        ActionExecutor([]).execute('FILE_REPORT', 100, 'C1-K1', Approval('lead', 'team_lead'))


def test_team_lead_cannot_block_large_exposure():
    with pytest.raises(PermissionDenied):
        ActionExecutor([]).execute('BLOCK_CARD', 3000, 'C1-K1', Approval('lead', 'team_lead'))


def test_manager_can_file_report():
    r = ActionExecutor([]).execute('FILE_REPORT', 100, 'C1-K1', Approval('mgr', 'fraud_manager'))
    assert r['status'] == 'executed'


def test_unknown_or_injected_action_rejected():
    with pytest.raises(PermissionDenied):
        ActionExecutor([]).execute('REFUND_EVERYONE', 1, 'C1-K1')


def test_auto_actions_execute():
    for a in ['CREATE_CASE', 'VERIFY_WITH_CUSTOMER', 'STEP_UP_AUTH', 'MONITOR_CARD', 'CLOSE_NO_FRAUD']:
        assert ActionExecutor([]).execute(a, 1, 'C1-K1')['status'] == 'executed'
