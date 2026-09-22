"""TigerGraph connection (Savanna or Community Edition) configured from .env"""
import os
from dotenv import load_dotenv

load_dotenv()


def connect():
    import pyTigerGraph as tg
    host = os.environ['TG_HOST']
    graph = os.environ.get('TG_GRAPH', 'FraudGraph')
    user = os.environ.get('TG_USERNAME', 'tigergraph')
    pwd = os.environ.get('TG_PASSWORD', '')
    secret = os.environ.get('TG_SECRET', '')
    token = os.environ.get('TG_API_TOKEN', '')
    kw = dict(host=host, graphname=graph, username=user, password=pwd)
    if secret:
        kw['gsqlSecret'] = secret
    if token:
        kw['apiToken'] = token
    conn = tg.TigerGraphConnection(**kw)
    if secret and not token:
        try:
            tok = conn.getToken(secret)
            conn.apiToken = tok[0] if isinstance(tok, (list, tuple)) else tok
        except Exception as e:  # token auth may be disabled on Community Edition
            print('getToken skipped:', e)
    return conn
