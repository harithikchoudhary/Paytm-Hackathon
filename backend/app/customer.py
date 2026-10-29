"""Fictional signed-in customer fixture. No insurer account or network connection."""
from copy import deepcopy

WORDING_URL = 'https://customer-portal-assets.hdfcergo.com/documents/PolicyWordings_myOptimaSecure-76673175551.pdf'
ISSUED_POLICY = {
    'id': 'customer-health-2026', 'number': 'DEMO-HEALTH-2026-001',
    'insurer': 'HDFC ERGO', 'product': 'my:Optima Secure', 'uin': 'HDFHLIP26058V082526',
    'start_date': '2026-04-02', 'end_date': '2027-04-01', 'sum_insured': 500000,
    'holder': 'Aarav Sharma', 'is_demo': True, 'wording_url': WORDING_URL,
    'members': [{'id': 'aarav', 'name': 'Aarav Sharma', 'relationship': 'Self', 'age': 34},
                {'id': 'meera', 'name': 'Meera Sharma', 'relationship': 'Spouse', 'age': 32}],
    'notice': 'Fictional issued schedule for a simulated customer. This is not insurance issued by HDFC ERGO. No live balance or eligibility is available.',
}
HOSPITALS = [
    {'id': 'sunrise-pune', 'name': 'Sunrise Care Hospital', 'city': 'Pune', 'area': 'Baner', 'network': 'sample_network', 'specialties': ['General medicine', 'Orthopaedics'], 'is_demo': True},
    {'id': 'harbour-mumbai', 'name': 'Harbour Medical Centre', 'city': 'Mumbai', 'area': 'Andheri', 'network': 'sample_network', 'specialties': ['General surgery', 'Cardiology'], 'is_demo': True},
    {'id': 'city-delhi', 'name': 'City Wellness Hospital', 'city': 'Delhi', 'area': 'Dwarka', 'network': 'unverified', 'specialties': ['General medicine'], 'is_demo': True},
]


def issued_policy(policy_id):
    return deepcopy(ISSUED_POLICY) if policy_id == ISSUED_POLICY['id'] else None


def process_clauses():
    # Concise summaries, NOT verbatim policy text or an eligibility rules engine.
    records = [
        ('H1', 'E.1.1 — Claim notification', 49, 'The wording specifies notice within 24 hours of emergency hospitalization or discharge, whichever is earlier; planned admission requires at least 48 hours notice.'),
        ('H2', 'E.1.2 — Cashless claims in India', 49, 'The hospital sends the cashless request and medical information. The insurer verifies it and decides pre-authorization. Patients may owe non-medical or inadmissible expenses.'),
        ('H3', 'E.1.5 — Cashless arrangements', 50, 'Check the insurer’s updated provider list. Cashless authorization is required; payment goes directly to the provider up to the authorized amount.'),
        ('H4', 'E.1.6 — Reimbursement timing', 50, 'The wording specifies reimbursement submission deadlines measured from discharge or completion of post-hospitalization treatment. Review the source for the applicable deadline.'),
        ('H5', 'E.1.7 — Supporting documents', 51, 'The reimbursement list includes a completed claim form, identity evidence, discharge summary, paid bills and bank documentation. Additional clinical and situation-specific evidence may be required.'),
    ]
    return [{'id': key, 'section': section, 'page': page, 'text': text, 'source_url': WORDING_URL,
             'source_name': 'HDFC ERGO my:Optima Secure wording', 'summary': True} for key, section, page, text in records]


def policy_context(app):
    if not app.get('issued_policy'):
        from .policies import CLAUSES, POLICY_ID
        return {'id': POLICY_ID, 'name': 'Intentra Health — Synthetic Policy v1', 'clauses': CLAUSES, 'pdf_url': '/api/policy/pdf', 'is_demo': True}
    clauses = process_clauses() + [
        {'id': 'P1', 'section': 'OneFlow — Preliminary reimbursement checks', 'page': 1, 'source_name': 'OneFlow POC checklist',
         'source_url': '/api/policy/checklist', 'text': 'This POC checks a preloaded fictional schedule, bill, discharge summary, and bank proof for consistency. A prepared preliminary packet does not satisfy all insurer requirements; check E.1.7 for the complete and conditional document list.'},
        {'id': 'P2', 'section': 'OneFlow — Cashless simulator checklist', 'page': 1, 'source_name': 'OneFlow POC checklist',
         'source_url': '/api/policy/checklist', 'text': 'The simulator requires a sample hospital arrangement, insured member, admission details, identity readiness, admission advice, and cost estimate. Every status and amount is simulated. No authorization request is sent and no insurance decision is made.'},
    ]
    return {'id': ISSUED_POLICY['uin'], 'name': 'HDFC ERGO my:Optima Secure — Process guidance', 'clauses': clauses,
            'pdf_url': WORDING_URL, 'is_demo': True}
