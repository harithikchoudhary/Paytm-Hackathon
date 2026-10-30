"""Evidence-bound policy checks for the supplied fictional schedule.

These checks intentionally return uncertainty when the uploaded evidence cannot
support a policy conclusion. They are not an insurer coverage decision.
"""
from datetime import date
from decimal import Decimal, InvalidOperation


def assess(app):
    policy = app.get('issued_policy')
    fields = app.get('fields', {})
    if not policy:
        return {'status': 'insufficient_policy', 'checks': [], 'explanation': 'A policy schedule is required before policy-specific eligibility can be assessed.', 'indicative_payable_amount': None}
    checks = []
    start = None
    admission = None
    try:
        start = date.fromisoformat(policy['start_date'])
        admission = date.fromisoformat(fields.get('admission_date', {}).get('value', ''))
    except ValueError:
        pass
    if start and admission:
        days = (admission - start).days
        checks.append({'id': 'initial_waiting_period', 'result': 'pass' if days >= 30 else 'uncertain', 'clause_id': 'H4', 'explanation': 'The 30-day illness waiting period is satisfied.' if days >= 30 else 'Admission is within the first 30 days; accident status and insurer confirmation are required.'})
    else:
        checks.append({'id': 'initial_waiting_period', 'result': 'unknown', 'clause_id': 'H4', 'explanation': 'Admission date evidence is required to assess the initial waiting period.'})
    treatment = str(fields.get('treatment_summary', {}).get('value', '')).casefold()
    exclusion_terms = {'cosmetic': 'Cosmetic procedures are excluded unless specifically covered.', 'unproven': 'Unproven treatments are excluded unless specifically covered.', 'non-medical': 'Non-medical expenses are excluded unless specifically covered.'}
    for term, explanation in exclusion_terms.items():
        if term in treatment:
            checks.append({'id': 'exclusion_' + term, 'result': 'uncertain', 'clause_id': 'H4', 'explanation': explanation})
    amount = None
    try:
        amount = Decimal(fields.get('bill_total', {}).get('value', '').replace(',', ''))
    except (InvalidOperation, AttributeError):
        pass
    eligible = None
    if amount is not None and amount.is_finite() and amount >= 0:
        eligible = min(amount, Decimal(str(policy['sum_insured'])))
        checks.extend([
            {'id': 'deductible', 'result': 'pass', 'clause_id': 'H3', 'explanation': 'The supplied schedule lists INR 0 deductible.'},
            {'id': 'copayment', 'result': 'pass', 'clause_id': 'H3', 'explanation': 'The supplied schedule lists 0% co-payment for eligible inpatient claims.'},
            {'id': 'sum_insured', 'result': 'pass' if amount <= policy['sum_insured'] else 'uncertain', 'clause_id': 'H3', 'explanation': 'The bill is within the base sum insured.' if amount <= policy['sum_insured'] else 'The bill exceeds the base sum insured; insurer adjudication is required.'},
        ])
    unknown = any(c['result'] in ('unknown', 'uncertain') for c in checks)
    return {'status': 'review_required' if unknown else 'indicative_only', 'checks': checks,
            'explanation': 'Indicative amount is shown only from supplied schedule limits; insurer adjudication remains authoritative.' if not unknown else 'Some policy conditions require insurer review before an amount can be estimated.',
            'indicative_payable_amount': str(eligible.quantize(Decimal('0.01'))) if eligible is not None and not unknown else None}
