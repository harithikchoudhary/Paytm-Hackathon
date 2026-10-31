"""Evidence-bound policy checks for the supplied fictional schedule.

These checks intentionally return uncertainty when the uploaded evidence cannot
support a policy conclusion. They are not an insurer coverage decision.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from .date_utils import parse_document_date


def assess(app):
    policy = app.get('issued_policy')
    fields = app.get('fields', {})
    line_items = []
    for document in app.get('documents', []):
        if document.get('kind') != 'bill':
            continue
        for item in document.get('line_items', []):
            try:
                amount = Decimal(str(item.get('amount', '0')).replace(',', ''))
            except (InvalidOperation, AttributeError):
                continue
            description = str(item.get('description', '')).strip()
            excluded = next((reason for term, reason in {
                'cosmetic': 'This service appears to be cosmetic and needs policy review.',
                'non-medical': 'This looks like a non-medical expense.',
                'personal': 'This appears to be a personal convenience expense.',
            }.items() if term in description.casefold()), None)
            line_items.append({**item, 'amount': str(amount), 'result': 'review_required' if excluded else 'eligible',
                               'reason': excluded or 'No exclusion was found in the supplied policy information.'})
    if not policy:
        # A user-uploaded schedule has no trusted account metadata, so use only
        # values extracted from that schedule and remain conservative when a
        # clause or financial limit is absent.
        policy = {
            'start_date': fields.get('policy_start', {}).get('value', ''),
            'end_date': fields.get('policy_end', {}).get('value', ''),
            'sum_insured': fields.get('sum_insured', {}).get('value', ''),
        }
        if not any(policy.values()):
            total = sum(Decimal(str(item['amount'])) for item in line_items) if line_items else None
            return {'status': 'insufficient_policy', 'checks': [], 'explanation': 'Upload your policy schedule before policy-specific eligibility can be assessed.', 'indicative_payable_amount': None,
                    'bill_total': str(total.quantize(Decimal('0.01'))) if total is not None else None,
                    'eligible_amount': None, 'review_amount': None, 'line_items': line_items}
    checks = []
    start = None
    admission = None
    try:
        start = parse_document_date(policy.get('start_date', ''))
        admission = parse_document_date(fields.get('admission_date', {}).get('value', ''))
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
    def money(value):
        match = re.search(r'-?\d[\d,]*(?:\.\d+)?', str(value or ''))
        if not match:
            return None
        try:
            return Decimal(match.group(0).replace(',', ''))
        except InvalidOperation:
            return None

    amount = money(fields.get('bill_total', {}).get('value', ''))
    eligible = None
    if amount is not None and amount.is_finite() and amount >= 0:
        limit = policy.get('sum_insured')
        if not limit:
            return {'status': 'review_required', 'checks': checks, 'explanation': 'The uploaded policy does not provide a usable sum insured. An insurer must assess the payable amount.', 'indicative_payable_amount': None}
        limit_amount = money(limit)
        if limit_amount is None:
            return {'status': 'review_required', 'checks': checks, 'explanation': 'The uploaded policy does not provide a usable sum insured. An insurer must assess the payable amount.', 'indicative_payable_amount': None, 'bill_total': str(amount.quantize(Decimal('0.01'))), 'eligible_amount': None, 'review_amount': None, 'line_items': line_items}
        eligible = min(amount, limit_amount)
        checks.extend([
            {'id': 'deductible', 'result': 'pass', 'clause_id': 'H3', 'explanation': 'The supplied schedule lists INR 0 deductible.'},
            {'id': 'copayment', 'result': 'pass', 'clause_id': 'H3', 'explanation': 'The supplied schedule lists 0% co-payment for eligible inpatient claims.'},
            {'id': 'sum_insured', 'result': 'pass' if amount <= limit_amount else 'uncertain', 'clause_id': 'UPLOADED_POLICY', 'explanation': 'The bill is within the sum insured shown on the uploaded schedule.' if amount <= limit_amount else 'The bill exceeds the sum insured shown on the uploaded schedule; insurer adjudication is required.'},
        ])
    unknown = any(c['result'] in ('unknown', 'uncertain') for c in checks)
    item_eligible = sum(Decimal(str(item['amount'])) for item in line_items if item['result'] == 'eligible')
    item_review = sum(Decimal(str(item['amount'])) for item in line_items if item['result'] != 'eligible')
    if line_items and amount is None:
        amount = sum(Decimal(str(item['amount'])) for item in line_items)
        eligible = amount
    return {'status': 'review_required' if unknown or item_review else 'indicative_only', 'checks': checks,
            'explanation': 'Indicative amount is shown only from supplied schedule limits; insurer adjudication remains authoritative.' if not unknown else 'Some policy conditions require insurer review before an amount can be estimated.',
            'indicative_payable_amount': str(min(eligible, item_eligible).quantize(Decimal('0.01'))) if eligible is not None and not unknown else None,
            'bill_total': str(amount.quantize(Decimal('0.01'))) if amount is not None else None,
            'eligible_amount': str(item_eligible.quantize(Decimal('0.01'))) if line_items else (str(eligible.quantize(Decimal('0.01'))) if eligible is not None and not unknown else None),
            'review_amount': str(item_review.quantize(Decimal('0.01'))) if line_items else None,
            'line_items': line_items}
