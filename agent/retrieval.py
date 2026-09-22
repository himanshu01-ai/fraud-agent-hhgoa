"""
GraphRAG context assembly.
  1. Graph-linked memory  : closed cases on the same card / touching the same device profile
                            (returned by GSQL traversals cases_by_card, cases_by_device)
  2. Typology memory      : closed cases whose analyst notes are most similar (TF-IDF) to the
                            evidence found, restricted to the same pattern (or cleared cases for
                            likely-legitimate alerts) - "how did we decide last time?"
  3. Policy / pattern text: the exact rule paragraphs the decision cites (rag/*.md)
Only this distilled context is handed to the LLM - never raw tables.
"""
import re
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel


class Retriever:
    def __init__(self, cc, policy_path='rag/fraud_policy.md', patterns_path='rag/fraud_patterns.md'):
        self.cc = cc.reset_index(drop=True)
        self.notes = self.cc.analyst_notes.fillna('').str.replace(r'Case CC-\d+: cardholder C\d+ ', '', regex=True)
        self.vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, stop_words='english')
        self.M = self.vec.fit_transform(self.notes)
        self.policy = open(policy_path).read()
        self.patterns = open(patterns_path).read()

    def typology(self, query, pattern, amount, k=3, cleared=False):
        mask = (self.cc.outcome == 'cleared') if cleared else (self.cc.pattern == pattern)
        idx = self.cc.index[mask]
        if not len(idx):
            return []
        sims = linear_kernel(self.vec.transform([query]), self.M[idx]).ravel()
        amt = self.cc.loc[idx, 'exposure_usd'].fillna(0).values
        # tie-break by amount closeness for cleared cases (their exposure is 0)
        score = sims - (0 if cleared else 0.02 * abs(amt - amount) / max(amount, 1))
        top = pd.Series(score, index=idx).sort_values(ascending=False).head(k).index
        return list(self.cc.loc[top, 'case_id'])

    def rule_text(self, rule):
        m = re.search(r'\*\*' + re.escape(rule) + r'\..*?(?=\n\n)', self.policy, re.S)
        return m.group(0) if m else ''

    def pattern_text(self, pattern):
        names = {'card_testing': 'Card testing', 'card_not_present_fraud': 'Card-not-present fraud.',
                 'card_not_present_new_device': 'from a new device', 'out_of_region_use': 'Out-of-region',
                 'account_takeover': 'Account takeover'}
        key = names.get(pattern)
        if not key:
            return ''
        for para in self.patterns.split('\n\n'):
            if key in para:
                return para.strip()
        return ''

    def notes_for(self, ids):
        d = self.cc[self.cc.case_id.isin(ids)]
        return {r.case_id: f'{r.outcome}/{r.pattern}: {str(r.analyst_notes)[:300]}' for r in d.itertuples()}
