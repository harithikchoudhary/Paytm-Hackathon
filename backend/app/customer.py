"""Fictional signed-in customer fixture. No insurer account or network connection."""
from pathlib import Path
from copy import deepcopy

POLICY_PDF_PATH = Path(__file__).resolve().parents[1] / 'data' / 'policies' / '01_OneFlow_Health_Policy.pdf'
WORDING_URL = '/api/customer/policies/customer-health-2026/file'
ISSUED_POLICY = {
    'id': 'customer-health-2026', 'number': 'OFH-2026-000184',
    'insurer': 'OneFlow Health Insurance Company', 'product': 'OneFlow Care Plus', 'uin': 'OF-CARE-PLUS-2026',
    'start_date': '2026-01-01', 'end_date': '2026-12-31', 'sum_insured': 500000,
    'holder': 'Amulya', 'is_demo': True, 'wording_url': WORDING_URL,
    # Keep the stable POC member id so existing saved test journeys remain compatible.
    'members': [{'id': 'aarav', 'name': 'Amulya', 'relationship': 'Self', 'age': 28}],
    'notice': 'Fictional testing policy supplied for the OneFlow POC. It is not insurance issued by a real insurer. No live balance or eligibility is available.',
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
        ('H1', 'Policy conditions — Medical necessity', 1, 'Hospitalization must be medically necessary and normally exceed 24 hours, except for covered day-care procedures.'),
        ('H2', 'Policy conditions — Cashless and reimbursement', 1, 'The schedule identifies both cashless and reimbursement as available claim routes; payment remains subject to verification, admissibility, available sum insured, and policy conditions.'),
        ('H3', 'Coverage and financial limits', 1, 'The base sum insured is INR 5,00,000 per policy year, with single private room eligibility up to INR 5,000 per day and a 0% co-payment for eligible inpatient claims.'),
        ('H4', 'Waiting periods and exclusions', 1, 'The schedule states a 30-day initial illness waiting period, 24 months for specified diseases, and 36 months for declared pre-existing diseases. Cosmetic, non-medical, and unproven treatments are excluded unless specifically covered.'),
        ('H5', 'Reimbursement submission', 2, 'For reimbursement, the schedule says to submit the claim within 30 days of discharge. Payment remains subject to verification, admissibility, available sum insured, and policy conditions.'),
    ]
    return [{'id': key, 'section': section, 'page': page, 'text': text, 'source_url': WORDING_URL,
             'source_name': 'OneFlow Care Plus policy supplied for this POC', 'summary': True} for key, section, page, text in records]


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
    return {'id': ISSUED_POLICY['uin'], 'name': 'OneFlow Care Plus — Policy guidance', 'clauses': clauses,
            'pdf_url': WORDING_URL, 'is_demo': True}


def customer_policy_document(policy, member_id):
    """Return the supplied policy PDF and the identity fields used by the POC."""
    member = next(m for m in policy['members'] if m['id'] == member_id)
    values = {'full_name': member['name'], 'policy_number': policy['number'],
              'policy_start': policy['start_date'], 'policy_end': policy['end_date']}
    labels = {'full_name': 'Policyholder / insured', 'policy_number': 'Policy number',
              'policy_start': 'Policy start', 'policy_end': 'Policy expiry'}
    extracted = [{'key': key, 'value': value, 'page': 1, 'quote': f'{labels[key]}: {value}'}
                 for key, value in values.items()]
    return POLICY_PDF_PATH.read_bytes(), extracted
