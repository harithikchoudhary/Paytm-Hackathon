"""Fictional signed-in customer fixture. No insurer account or network connection."""
from pathlib import Path
from copy import deepcopy

POLICY_PDF_PATH = Path(__file__).resolve().parents[1] / 'data' / 'policies' / '01_OneFlow_Health_Policy.pdf'
WORDING_URL = '/api/customer/policies/customer-health-2026/file'
ISSUED_POLICY = {
    'id': 'customer-health-2026', 'number': 'OFH-2026-000184',
    'insurer': 'OneFlow Health Insurance Company', 'product': 'OneFlow Care Plus', 'uin': 'OF-CARE-PLUS-2026',
    'start_date': '2026-01-01', 'end_date': '2026-12-31', 'sum_insured': 500000,
    'holder': 'Policy holder', 'is_demo': True, 'wording_url': WORDING_URL,
    # Keep the stable member id so existing saved journeys remain compatible.
    'members': [{'id': 'aarav', 'name': 'Policy holder', 'relationship': 'Self', 'age': 0}],
    'notice': 'This policy is a local test record. It is not connected to a live insurer account or balance.',
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
             'source_name': 'OneFlow Care Plus policy supplied for this application', 'summary': True} for key, section, page, text in records]


def policy_context(app):
    if not app.get('issued_policy'):
        uploaded = [d for d in app.get('documents', []) if d.get('kind') == 'policy']
        if not uploaded:
            return {'id': None, 'name': 'Upload your policy to see policy guidance', 'clauses': [], 'pdf_url': None, 'is_demo': False}
        clauses = []
        for document in uploaded:
            for field in document.get('extracted', []):
                clauses.append({
                    'id': 'UP-' + field['key'],
                    'section': 'Uploaded policy schedule',
                    'page': field.get('page', 1),
                    'source_name': document.get('name', 'Uploaded policy schedule'),
                    'source_url': f"/api/applications/{app.get('id')}/documents/{document['id']}/file",
                    'text': f"{field.get('key', 'Policy detail')}: {field.get('value', '')}",
                })
        return {'id': 'uploaded-policy', 'name': 'Your uploaded policy schedule', 'clauses': clauses, 'pdf_url': None, 'is_demo': False}
    clauses = process_clauses() + [
        {'id': 'P1', 'section': 'OneFlow — Preliminary reimbursement checks', 'page': 1, 'source_name': 'OneFlow checklist',
         'source_url': '/api/policy/checklist', 'text': 'The checklist compares the policy schedule, hospital bill, discharge summary, and bank proof for consistency. A prepared packet does not satisfy all insurer requirements; review the insurer document list and conditions.'},
        {'id': 'P2', 'section': 'OneFlow — Cashless simulator checklist', 'page': 1, 'source_name': 'OneFlow checklist',
         'source_url': '/api/policy/checklist', 'text': 'The simulator requires a sample hospital arrangement, insured member, admission details, identity readiness, admission advice, and cost estimate. Every status and amount is simulated. No authorization request is sent and no insurance decision is made.'},
    ]
    return {'id': ISSUED_POLICY['uin'], 'name': 'OneFlow Care Plus — Policy guidance', 'clauses': clauses,
            'pdf_url': WORDING_URL, 'is_demo': True}


def customer_policy_document(policy, member_id):
    """Return the supplied policy PDF and identity fields for the journey."""
    member = next(m for m in policy['members'] if m['id'] == member_id)
    values = {'full_name': member['name'], 'policy_number': policy['number'],
              'policy_start': policy['start_date'], 'policy_end': policy['end_date']}
    labels = {'full_name': 'Policyholder / insured', 'policy_number': 'Policy number',
              'policy_start': 'Policy start', 'policy_end': 'Policy expiry'}
    extracted = [{'key': key, 'value': value, 'page': 1, 'quote': f'{labels[key]}: {value}'}
                 for key, value in values.items()]
    return POLICY_PDF_PATH.read_bytes(), extracted
