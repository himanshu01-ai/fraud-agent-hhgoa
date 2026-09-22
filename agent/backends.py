"""
Graph access layer.  Every investigation step goes through one of these "tools", so the agent
logic is identical whether the graph lives in TigerGraph (Savanna / CE, via pyTigerGraph or the
TigerGraph MCP server) or in the local feature store used for offline reproducibility.

Each call is logged (name, params, rows) -> becomes the case's tool trace, `tool_calls`, and the
`ref` of every evidence item.
"""
import json, os, asyncio
import pandas as pd

STD = ['TransactionID', 'card_id', 'customer_id', 'ts', 'TransactionAmt', 'ProductCD', 'channel', 'addr1',
       'P_emaildomain', 'R_emaildomain', 'risk_score', 'p_model', 'device_profile', 'id_15', 'id_23', 'uid',
       'M4', 'M6']
GENERIC_PROFILE_PREFIX = ('NA | NA | NA', )


class Backend:
    name = 'base'

    def __init__(self):
        self.calls = []

    def _log(self, tool, params, n):
        self.calls.append({'tool': tool, 'params': params, 'rows': n})

    def reset_log(self):
        self.calls = []


# --------------------------------------------------------------------------------------------
class LocalBackend(Backend):
    """Pandas mirror of the TigerGraph schema (same traversals, same outputs)."""
    name = 'local'

    def __init__(self, core='data/tx_core.pkl', scores='data/scores.pkl', cc_path=None, memory='data/case_memory.json'):
        super().__init__()
        tx = pd.read_pickle(core)
        if os.path.exists(scores):
            tx = tx.merge(pd.read_pickle(scores), on='TransactionID', how='left')
        else:
            tx['p_model'] = float('nan')
        self.tx = tx[STD].sort_values('ts').reset_index(drop=True)
        self.by_id = pd.Series(self.tx.index, index=self.tx.TransactionID)
        self.by_card = self.tx.groupby('card_id').indices
        self.by_dev = self.tx.groupby('device_profile').indices
        self.by_uid = self.tx.groupby('uid').indices
        self.cc = pd.read_csv(cc_path)
        m = self.cc.assign(t=self.cc.txn_ids.astype(str).str.split('|')).explode('t')
        self.cc_by_txn = m.groupby(m.t.astype(int)).case_id.apply(list).to_dict()
        self.memory_path = memory
        self.exclude = None   # backtests: hide the case being replayed from memory
        self.memory = json.load(open(memory)) if os.path.exists(memory) else []

    def get_txn(self, txn_id):
        self._log('get_txn', {'txn_id': txn_id}, 1)
        return self.tx.loc[self.by_id[int(txn_id)]]

    def card_txns(self, card_id, t_from, t_to):
        idx = self.by_card.get(card_id, [])
        d = self.tx.iloc[idx]
        d = d[(d.ts >= t_from) & (d.ts <= t_to)]
        self._log('card_txns', {'card_id': card_id, 't_from': str(t_from), 't_to': str(t_to)}, len(d))
        return d

    def device_txns(self, profile, t_from, t_to):
        idx = self.by_dev.get(profile, [])
        d = self.tx.iloc[idx]
        d = d[(d.ts >= t_from) & (d.ts <= t_to)]
        self._log('device_txns', {'device': profile, 't_from': str(t_from), 't_to': str(t_to)}, len(d))
        return d

    def device_footprint(self, profile):
        d = self.tx.iloc[self.by_dev.get(profile, [])]
        self._log('device_footprint', {'device': profile}, 1)
        return {'n_txns': len(d), 'n_cards': d.card_id.nunique(), 'n_customers': d.customer_id.nunique()}

    def cardholder_txns(self, uid):
        d = self.tx.iloc[self.by_uid.get(uid, [])]
        self._log('cardholder_txns', {'uid': uid}, len(d))
        return d

    def cases_by_card(self, card_id):
        d = self.cc[((self.cc.card_id == card_id) | self.cc.connected_card_ids.fillna('').str.contains(card_id))
                    & (self.cc.case_id != self.exclude)]
        self._log('cases_by_card', {'card_id': card_id}, len(d))
        return d

    def cases_by_device(self, profile):
        ids = set()
        for t in self.tx.TransactionID.values[self.by_dev.get(profile, [])]:
            ids.update(self.cc_by_txn.get(int(t), []))
        d = self.cc[self.cc.case_id.isin(ids) & (self.cc.case_id != self.exclude)]
        self._log('cases_by_device', {'device': profile}, len(d))
        return d

    def closed_cases(self):
        return self.cc

    def fraud_proximity(self, card_id, t_from, t_to, max_customers=200):
        d = self.tx.iloc[self.by_card.get(card_id, [])]
        d = d[(d.ts >= t_from) & (d.ts <= t_to)]
        ids = set()
        for prof in set(d.device_profile.dropna()):
            if prof.startswith('NA | NA'):
                continue
            idx = self.by_dev.get(prof, [])
            if self.tx.customer_id.values[idx].size and len(set(self.tx.customer_id.values[idx])) > max_customers:
                continue
            for t in self.tx.TransactionID.values[idx]:
                ids.update(self.cc_by_txn.get(int(t), []))
        conf = sorted(self.cc[self.cc.case_id.isin(ids) & (self.cc.outcome == 'confirmed_fraud') & (self.cc.case_id != self.exclude)].case_id)
        self._log('fraud_proximity', {'card_id': card_id}, len(conf))
        return {'cases': conf}

    def ring_scan(self, t_from, t_to, min_cards=3, max_customers=60):
        w = self.tx[(self.tx.ts >= t_from) & (self.tx.ts <= t_to) & self.tx.device_profile.notna()]
        w = w[~w.device_profile.str.startswith('NA | NA')]
        tot = self.tx.groupby('device_profile').customer_id.nunique()
        g = w.groupby('device_profile').agg(cards=('card_id', lambda s: sorted(set(s))), n_txns=('TransactionID', 'size'),
                                            n_new=('id_15', lambda s: int((s == 'New').sum())),
                                            n_proxy=('id_23', lambda s: int(s.isin(['IP_PROXY:ANONYMOUS', 'IP_PROXY:HIDDEN']).sum())))
        g = g[(g.cards.str.len() >= min_cards) & (tot.reindex(g.index) <= max_customers)]
        self._log('ring_scan', {'t_from': str(t_from), 't_to': str(t_to)}, len(g))
        return g.reset_index()

    def case_memory(self, pattern, profile):
        r = [m for m in self.memory if m.get('pattern') == pattern or (profile and profile in m.get('devices', []))]
        self._log('case_memory', {'pattern': pattern, 'device': profile}, len(r))
        return r

    def write_case(self, rec, answer):
        self.memory = [m for m in self.memory if m['graph_case_id'] != rec['graph_case_id']] + [rec]
        json.dump(self.memory, open(self.memory_path, 'w'), indent=1, default=str)
        self._log('write_case(local)', {'id': rec['graph_case_id']}, 1)
        return False  # local store is not TigerGraph


# --------------------------------------------------------------------------------------------
TG_MAP = {'id': 'TransactionID', 'amt': 'TransactionAmt', 'product': 'ProductCD', 'p_email': 'P_emaildomain',
          'r_email': 'R_emaildomain', 'device': 'device_profile', 'm4': 'M4', 'm6': 'M6'}


class TigerGraphBackend(Backend):
    """Runs the installed GSQL queries (graph/queries.gsql) and writes cases back to the graph."""
    name = 'tigergraph'

    def __init__(self, cc_path=None, use_mcp=False):
        super().__init__()
        from agent.tg_conn import connect
        self.conn = connect()
        self.use_mcp = use_mcp
        self.mcp = MCPClient() if use_mcp else None
        self.cc = pd.read_csv(cc_path)  # retrieval corpus (also stored as ClosedCase vertices)

    def _q(self, name, params):
        if self.mcp:
            res = self.mcp.run_installed_query(name, params)
        else:
            res = self.conn.runInstalledQuery(name, params)
        return res

    @staticmethod
    def _txn_df(res, key='T'):
        rows = []
        for block in res:
            for v in block.get(key, []):
                a = dict(v['attributes'])
                a['id'] = v['v_id']
                rows.append(a)
        d = pd.DataFrame(rows).rename(columns=TG_MAP)
        if d.empty:
            return pd.DataFrame(columns=STD)
        d['TransactionID'] = d.TransactionID.astype(int)
        d['ts'] = pd.to_datetime(d.ts)
        d['addr1'] = pd.to_numeric(d.addr1.replace('', None), errors='coerce')
        for c in ['device_profile', 'P_emaildomain', 'R_emaildomain', 'id_15', 'id_23', 'uid', 'M4', 'M6']:
            d[c] = d[c].replace('', None)
        return d[STD].sort_values('ts')

    def get_txn(self, txn_id):
        v = self.conn.getVerticesById('Txn', str(txn_id))
        self._log('get_txn', {'txn_id': txn_id}, 1)
        return self._txn_df([{'T': v}]).iloc[0]

    def card_txns(self, card_id, t_from, t_to):
        d = self._txn_df(self._q('card_txns', {'c': card_id, 't_from': str(t_from)[:19], 't_to': str(t_to)[:19]}))
        self._log('card_txns', {'card_id': card_id, 't_from': str(t_from), 't_to': str(t_to)}, len(d))
        return d

    def device_txns(self, profile, t_from, t_to):
        d = self._txn_df(self._q('device_txns', {'d': profile, 't_from': str(t_from)[:19], 't_to': str(t_to)[:19]}))
        self._log('device_txns', {'device': profile, 't_from': str(t_from), 't_to': str(t_to)}, len(d))
        return d

    def device_footprint(self, profile):
        r = self._q('device_footprint', {'d': profile})
        out = {}
        for b in r:
            out.update(b)
        self._log('device_footprint', {'device': profile}, 1)
        return out

    def cardholder_txns(self, uid):
        d = self._txn_df(self._q('cardholder_txns', {'h': uid}))
        self._log('cardholder_txns', {'uid': uid}, len(d))
        return d

    def _cases(self, res):
        ids = [v['v_id'] for b in res for v in b.get('C', [])]
        return self.cc[self.cc.case_id.isin(ids)]

    def cases_by_card(self, card_id):
        d = self._cases(self._q('cases_by_card', {'c': card_id}))
        self._log('cases_by_card', {'card_id': card_id}, len(d))
        return d

    def cases_by_device(self, profile):
        d = self._cases(self._q('cases_by_device', {'d': profile}))
        self._log('cases_by_device', {'device': profile}, len(d))
        return d

    def closed_cases(self):
        return self.cc

    def fraud_proximity(self, card_id, t_from, t_to):
        r = self._q('fraud_proximity', {'c': card_id, 't_from': str(t_from)[:19], 't_to': str(t_to)[:19],
                                         'max_customers': 200})
        cases = sorted({v['v_id'] for blk in r for v in blk.get('C', [])})
        self._log('fraud_proximity', {'card_id': card_id}, len(cases))
        return {'cases': cases}

    def case_memory(self, pattern, profile):
        try:
            r = self._q('case_memory', {'pat': pattern, 'd': profile or 'NONE'})
            out = [dict(v['attributes']) for b in r for k in ('R', 'RD') for v in b.get(k, [])]
        except Exception:
            out = []
        self._log('case_memory', {'pattern': pattern, 'device': profile}, len(out))
        return out

    def write_case(self, rec, answer):
        c = self.conn
        gid = rec['graph_case_id']
        c.upsertVertex('InvestigationCase', gid, {
            'case_id': rec['case_id'], 'opened_at': rec['opened_at'], 'trigger_type': rec['trigger_type'],
            'status': rec['status'], 'verdict': rec['verdict'], 'fraud_probability': rec['fraud_probability'],
            'pattern': rec['pattern'], 'pattern_description': rec['pattern_description'],
            'exposure_usd': rec['exposure_usd'], 'sar_filed': rec['sar_filed'],
            'final_actions': '|'.join(rec['final_actions']), 'summary': rec['summary'],
            'answer_json': json.dumps({'answer': answer, 'decision_history': rec.get('decision_history', [])})})
        c.upsertEdge('InvestigationCase', gid, 'INV_ON_CARD', 'Card', rec['card_id'])
        for t in rec['affected_txn_ids']:
            c.upsertEdge('InvestigationCase', gid, 'INV_AFFECTS', 'Txn', str(t))
        for k in rec['connected_card_ids']:
            c.upsertEdge('InvestigationCase', gid, 'INV_CONNECTED', 'Card', k)
        for d in rec['devices']:
            c.upsertEdge('InvestigationCase', gid, 'INV_DEVICE', 'DeviceProfile', d)
        for s in rec['similar_prior_cases']:
            c.upsertEdge('InvestigationCase', gid, 'INV_SIMILAR', 'ClosedCase', s)
        self._log('write_case(tigergraph)', {'id': gid}, 1)
        return True


# --------------------------------------------------------------------------------------------
class MCPClient:
    """Calls installed queries through the official TigerGraph MCP server (pip install tigergraph-mcp).
    Tool names are discovered at start-up so it survives server version changes."""

    def __init__(self):
        from mcp import ClientSession, StdioServerParameters  # noqa: F401
        self.params = StdioServerParameters(command=os.environ.get('TG_MCP_CMD', 'tigergraph-mcp'),
                                            args=[], env=dict(os.environ))
        self.tool, self.schema = asyncio.run(self._discover())

    async def _discover(self):
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
        async with stdio_client(self.params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                tools = (await s.list_tools()).tools
                for t in tools:
                    if 'installed_query' in t.name or t.name.endswith('run_query'):
                        return t.name, t.inputSchema
        raise RuntimeError('No run-installed-query tool found on the TigerGraph MCP server')

    def run_installed_query(self, name, params):
        props = list((self.schema or {}).get('properties', {}).keys())
        qk = next((p for p in props if 'name' in p), 'query_name')
        pk = next((p for p in props if 'param' in p), 'params')
        args = {qk: name, pk: params}
        if 'graph_name' in props:
            args['graph_name'] = os.environ.get('TG_GRAPH', 'FraudGraph')
        return asyncio.run(self._call(args))

    async def _call(self, args):
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
        async with stdio_client(self.params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool(self.tool, args)
                txt = ''.join(getattr(c, 'text', '') for c in res.content)
                data = json.loads(txt)
                if isinstance(data, dict):
                    data = data.get('results', data.get('result', [data]))
                return data
