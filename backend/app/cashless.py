from datetime import date
from decimal import Decimal, InvalidOperation
from .customer import HOSPITALS
from . import store

TRANSITIONS = {
    'draft': {'submit': 'submitted'},
    'submitted': {'request_information': 'information_required', 'authorize': 'authorized', 'decline': 'declined'},
    'information_required': {'resubmit': 'resubmitted'},
    'resubmitted': {'request_information': 'information_required', 'authorize': 'authorized', 'decline': 'declined'},
    'authorized': {'discharge_review': 'discharge_review'},
    'discharge_review': {'settle': 'settled'},
    'declined': {}, 'settled': {},
}


def invalidate(app):
    cashless = app.get('cashless')
    if cashless and cashless['status'] not in ('draft', 'information_required'):
        cashless['status'] = 'draft'
        cashless['authorized_amount'] = None
        cashless['timeline'].append({'at': store.now(), 'status': 'draft', 'source': 'simulation',
            'message': 'Application details changed. The simulated request was reset; prepare and submit a new simulation.'})


def check(app):
    cashless = app['cashless']
    details = cashless['details']
    policy = app['issued_policy']
    issues = []
    def issue(code, message, clause='H2'):
        issues.append({'code': code, 'message': message, 'severity': 'error', 'clause_id': clause, 'field': None})
    hospital = next((h for h in HOSPITALS if h['id'] == details.get('hospital_id')), None)
    if not hospital:
        issue('hospital', 'Choose a hospital for the cashless assistance request.', 'H3')
    elif hospital['network'] != 'sample_network':
        issue('network', 'Hospital arrangement is unverified. Contact the hospital insurance desk or insurer. The simulator requires a sample network hospital.', 'H3')
    if details.get('member_id') not in {m['id'] for m in policy['members']}:
        issue('member', 'Select an insured member from your existing policy.')
    if details.get('admission_type') not in ('planned', 'emergency'):
        issue('admission_type', 'Select planned or emergency admission.', 'H1')
    try:
        admission = date.fromisoformat(details.get('admission_date', ''))
        if not date.fromisoformat(policy['start_date']) <= admission <= date.fromisoformat(policy['end_date']):
            issue('period', 'Admission date falls outside the fictional policy period. Insurer verification is required.', 'H1')
    except ValueError:
        issue('admission_date', 'Provide a valid admission date in YYYY-MM-DD format.', 'H1')
    if len(details.get('treatment_summary', '').strip()) < 10:
        issue('treatment', 'Add a short description of the admission or treatment advised by the hospital.')
    try:
        amount = Decimal(details.get('estimated_amount', ''))
        if not amount.is_finite() or amount <= 0:
            raise InvalidOperation
    except InvalidOperation:
        issue('estimate', 'Provide a positive estimated treatment cost.')
    if not details.get('identity_ready'):
        issue('identity', 'Confirm that the patient has identity evidence and the policy details available.')
    kinds = {d['kind'] for d in app['documents']}
    for kind, label in [('admission_advice', 'hospital admission advice'), ('cost_estimate', 'hospital cost estimate')]:
        if kind not in kinds:
            issue('missing_' + kind, f'Add the {label} for the simulated hospital handoff.')
    if cashless['status'] in ('authorized', 'discharge_review'):
        for kind, label in [('bill', 'final hospital bill'), ('discharge', 'discharge summary')]:
            if kind not in kinds:
                issue('missing_' + kind, f'Add the {label} before simulated final bill review.', 'H5')
    # Compare clinical document names against the selected policy member.
    member = next((m for m in policy['members'] if m['id'] == details.get('member_id')), None)
    for doc in app['documents']:
        expected = {'admission_advice': ['full_name', 'hospital_name', 'admission_date', 'treatment_summary'],
                    'cost_estimate': ['full_name', 'hospital_name', 'estimated_amount']}.get(doc['kind'], [])
        present = {f['key'] for f in doc['extracted']}
        if any(key not in present for key in expected):
            issue('incomplete_' + doc['id'], f'{doc["name"]} is missing verifiable handoff details. Replace it with clearer admission advice or cost evidence.', 'P2')
        for field in doc['extracted']:
            if member and field['key'] == 'full_name' and field['value'].strip().casefold() != member['name'].casefold():
                issue('patient_' + doc['id'], f'{doc["name"]} identifies a different patient. Replace the document or select the correct insured member.')
            if doc['kind'] in ('admission_advice', 'cost_estimate'):
                if hospital and field['key'] == 'hospital_name' and field['value'].strip().casefold() != hospital['name'].casefold():
                    issue('hospital_' + doc['id'], f'{doc["name"]} names a different hospital. Check the hospital selection or replace the document.')
                if field['key'] == 'admission_date' and details.get('admission_date') and field['value'] != details['admission_date']:
                    issue('date_' + doc['id'], 'Admission advice and the entered admission date differ. Check both sources.')
                if field['key'] == 'estimated_amount':
                    try:
                        if Decimal(field['value'].replace(',', '')) != Decimal(details.get('estimated_amount', '')):
                            issue('cost_' + doc['id'], 'The entered treatment estimate differs from the hospital estimate. Check both sources.')
                    except InvalidOperation:
                        issue('cost_' + doc['id'], 'The hospital estimate amount could not be compared. Verify the entered cost.')
    app['issues'] = issues
    app['status'] = 'cashless_' + cashless['status']
    app['progress'] = {'draft': 20 if issues else 40, 'submitted': 55, 'information_required': 55,
        'resubmitted': 65, 'authorized': 75, 'declined': 55, 'discharge_review': 90, 'settled': 100}[cashless['status']]
    cashless['hospital'] = hospital
    return app


def transition(app, action, clarification=''):
    app = check(app)
    cashless = app['cashless']
    current = cashless['status']
    target = TRANSITIONS[current].get(action)
    if not target:
        raise ValueError(f'Action {action} is not available from {current}.')
    if action in ('submit', 'resubmit', 'authorize', 'discharge_review', 'settle') and app['issues']:
        raise ValueError('Resolve the preparation checklist before advancing the simulation.')
    if action == 'resubmit' and len(clarification.strip()) < 10:
        raise ValueError('Add the requested clarification before resubmitting the simulation.')
    messages = {
        'submitted': 'Simulated hospital request submitted. No request was sent to an insurer or TPA.',
        'information_required': 'Simulated query: explain the estimated procedure costs or upload a revised hospital estimate.',
        'resubmitted': 'Simulated clarification received: ' + clarification.strip(),
        'authorized': 'Simulated authorization only. The example amount is not a coverage decision, benefit calculation, or promise of payment.',
        'declined': 'Simulated cashless decline. This does not determine reimbursement eligibility. Ask the insurer for the actual reason and next steps.',
        'discharge_review': 'Simulated final bill review. Actual payable amounts and patient contributions require insurer confirmation.',
        'settled': 'Simulated settlement complete. No funds were transferred.',
    }
    if action == 'authorize':
        # The simulator records the requested estimate as the decision amount.
        # A real adapter would return the insurer's calculated eligible amount.
        cashless['authorized_amount'] = str(Decimal(cashless['details']['estimated_amount']).quantize(Decimal('0.01')))
    cashless['status'] = target
    cashless['timeline'].append({'at': store.now(), 'status': target, 'message': messages[target], 'source': 'simulation'})
    store.mutate(app, 'cashless_simulation_' + target, {'simulation': True, 'message': messages[target]})
    return check(app)
