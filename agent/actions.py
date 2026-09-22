"""
Actions, permissions and approvals — enforced in CODE, not in a prompt.

* PERMISSIONS is the single source of truth for Fraud Policy §2 approval routing.
* ActionExecutor.execute() runs the mock action API only if the route allows it:
    auto -> the agent may execute alone
    L1   -> needs an Approval from a team lead (or fraud manager)
    L2   -> needs an Approval from a fraud manager
  Anything else raises PermissionDenied, whatever the LLM or the caller asks for.
* Every attempt (executed, pending, denied) is appended to the decision history.
Mock APIs stand in for card systems, CRM, customer messaging and the regulator gateway.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

ACTIONS = ['ALLOW_TRANSACTION', 'DECLINE_TRANSACTION', 'MONITOR_CARD', 'MONITOR_CONNECTED_CARDS', 'WARN_CUSTOMER',
           'VERIFY_WITH_CUSTOMER', 'STEP_UP_AUTH', 'BLOCK_CARD', 'BLOCK_ALL_CARDS', 'GENERATE_REPORT', 'CREATE_CASE',
           'FILE_REPORT', 'ESCALATE_TO_ANALYST', 'CLOSE_NO_FRAUD']
AUTO = {'ALLOW_TRANSACTION', 'MONITOR_CARD', 'MONITOR_CONNECTED_CARDS', 'WARN_CUSTOMER', 'VERIFY_WITH_CUSTOMER',
        'STEP_UP_AUTH', 'GENERATE_REPORT', 'CREATE_CASE', 'ESCALATE_TO_ANALYST', 'CLOSE_NO_FRAUD'}
LEVEL = {'auto': 0, 'L1': 1, 'L2': 2}
ROLE_LEVEL = {'agent': 0, 'team_lead': 1, 'fraud_manager': 2}


class PermissionDenied(Exception):
    pass


def required_route(action, exposure_usd):
    """Fraud Policy §2 — the only place routes are computed."""
    if action not in ACTIONS:
        raise PermissionDenied(f'unknown action {action!r}')
    if action in AUTO:
        return 'auto'
    if action == 'DECLINE_TRANSACTION':
        return 'L1'
    if action == 'BLOCK_CARD':
        return 'L1' if exposure_usd <= 2500 else 'L2'
    return 'L2'  # BLOCK_ALL_CARDS, FILE_REPORT


@dataclass
class Approval:
    approver: str
    role: str          # team_lead | fraud_manager
    note: str = ''


class ActionExecutor:
    def __init__(self, history):
        self.history = history   # shared decision history list (the case's audit trail)

    def _log(self, action, route, status, detail):
        self.history.append({'at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'action': action,
                             'route': route, 'status': status, 'detail': detail})

    def execute(self, action, exposure_usd, target, approval: Approval = None):
        route = required_route(action, exposure_usd)
        have = ROLE_LEVEL.get(approval.role, -1) if approval else 0
        if LEVEL[route] > have:
            self._log(action, route, 'pending_approval' if approval is None else 'denied',
                      f'requires {route}; ' + ('no approval supplied' if approval is None else
                                               f'{approval.role} is not sufficient'))
            if approval is not None:
                raise PermissionDenied(f'{action} requires {route}; {approval.role} cannot approve')
            return {'action': action, 'route': route, 'status': 'pending_approval'}
        result = MOCK_API[action](target)
        self._log(action, route, 'executed', result + (f' (approved by {approval.approver})' if approval else ''))
        return {'action': action, 'route': route, 'status': 'executed', 'result': result}


# ---- mock downstream systems -------------------------------------------------------------
MOCK_API = {
    'ALLOW_TRANSACTION': lambda t: f'authorization {t} released',
    'DECLINE_TRANSACTION': lambda t: f'authorization on {t} declined',
    'MONITOR_CARD': lambda t: f'{t} monitoring sensitivity raised for 72h',
    'MONITOR_CONNECTED_CARDS': lambda t: f'connected cards of {t} added to watch-list',
    'WARN_CUSTOMER': lambda t: f'informational message queued for holder of {t}',
    'VERIFY_WITH_CUSTOMER': lambda t: f'verification request sent to holder of {t}',
    'STEP_UP_AUTH': lambda t: f'one-time-passcode required on {t}',
    'BLOCK_CARD': lambda t: f'{t} blocked, reissue ordered',
    'BLOCK_ALL_CARDS': lambda t: f'all cards of the holder of {t} blocked',
    'GENERATE_REPORT': lambda t: f'internal report generated for {t}',
    'CREATE_CASE': lambda t: f'case opened for {t}',
    'FILE_REPORT': lambda t: f'SAR submitted to regulator gateway for {t}',
    'ESCALATE_TO_ANALYST': lambda t: f'case for {t} placed in analyst queue',
    'CLOSE_NO_FRAUD': lambda t: f'alert on {t} closed as legitimate',
}
