"""Baseline checklist rules used when an uploaded policy has not supplied a clause."""
import re

POLICY_ID = 'intentra-health-demo-v1'
POLICY_NUMBER = 'OF-2026-001'
CLAUSES = [
    {'id': 'C1', 'section': '1. Required documents', 'page': 1,
     'text': 'A reimbursement packet requires the policy schedule, an itemized hospital bill, a discharge summary, and bank account proof.'},
    {'id': 'C2', 'section': '2. Consistent patient details', 'page': 1,
     'text': 'Patient names must agree across the policy schedule, hospital bill, and discharge summary. The policy number must match the schedule supplied by the policyholder.'},
    {'id': 'C3', 'section': '3. Treatment dates', 'page': 1,
     'text': 'Admission must be on or before discharge. Both dates must fall within the policy period shown on the schedule. The bill and discharge summary must identify the same treatment dates.'},
    {'id': 'C4', 'section': '4. Bill and bank details', 'page': 2,
     'text': 'The packet must include a positive hospital bill total in INR, the hospital name, and the last four digits of the reimbursement bank account. Any amount above the sum insured shown on the policy schedule requires manual review.'},
    {'id': 'C5', 'section': '5. Review and submission', 'page': 2,
     'text': 'The applicant must review and confirm all extracted details before export. Packet readiness means checklist completion only. Coverage, medical necessity, payout, and claim approval require insurer review.'},
]


def retrieve(question, limit=3, corpus=None):
    synonyms = {'missing': 'required documents', 'upload': 'required documents',
                'name': 'patient names consistent', 'amount': 'bill total',
                'account': 'bank', 'covered': 'coverage approval', 'eligible': 'coverage approval',
                'ready': 'review submission', 'date': 'treatment dates period',
                'cashless': 'cashless hospital authorization', 'emergency': 'emergency notification',
                'planned': 'planned notification', 'hospital': 'provider cashless', 'preauth': 'authorization'}
    q = question.lower()
    q += ' ' + ' '.join(v for k, v in synonyms.items() if k in q)
    tokens = set(re.findall(r'[a-z]{3,}', q)) - {'the', 'and', 'what', 'how', 'can', 'for', 'this', 'you'}
    ranked = sorted(corpus if corpus is not None else CLAUSES, key=lambda c: sum(t in (c['text'] + ' ' + c['section']).lower() for t in tokens), reverse=True)
    matched = [c for c in ranked if any(t in (c['text'] + ' ' + c['section']).lower() for t in tokens)]
    return matched[:limit]


def citation(clause_id):
    return next(c for c in CLAUSES if c['id'] == clause_id)
