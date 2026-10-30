from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from .models import FIELDS
from .policies import POLICY_NUMBER
from .eligibility import assess

REQUIRED_DOCS = {'policy': 'Policy schedule', 'bill': 'Hospital bill', 'discharge': 'Discharge summary', 'bank_proof': 'Bank account proof'}
REQUIRED_FIELDS = ['full_name', 'policy_number', 'admission_date', 'discharge_date', 'hospital_name', 'bill_total', 'bank_account_last4', 'policy_start', 'policy_end']
EXPECTED = {'policy': ['full_name', 'policy_number', 'policy_start', 'policy_end'],
            'bill': ['full_name', 'hospital_name', 'bill_total', 'admission_date', 'discharge_date'],
            'discharge': ['full_name', 'hospital_name', 'admission_date', 'discharge_date'],
            'bank_proof': ['bank_account_last4'],
            'admission_advice': ['full_name', 'hospital_name', 'admission_date', 'treatment_summary'],
            'cost_estimate': ['full_name', 'hospital_name', 'estimated_amount']}
EXPECTED['clarification'] = []


class WorkflowState(TypedDict):
    application: dict


def assemble(state):
    app = state['application']
    fields = {key: {'key': key, 'label': label, 'value': '', 'sources': [], 'confirmed': False} for key, label in FIELDS.items()}
    for doc in app['documents']:
        for item in doc['extracted']:
            if item['key'] not in EXPECTED[doc['kind']]:
                continue
            f = fields[item['key']]
            f['sources'].append({**item, 'document_id': doc['id'], 'document_name': doc['name'], 'kind': doc['kind']})
            if not f['value']:
                f['value'] = item['value']
    for key, value in app['corrections'].items():
        fields[key]['value'] = value
        fields[key]['confirmed'] = True
    app['fields'] = fields
    return {'application': app}


def validate(state):
    app = state['application']
    issues = []
    def issue(code, message, clause, severity='error', field=None):
        if app.get('issued_policy'):
            clause = 'P1'
        issues.append({'code': code, 'message': message, 'clause_id': clause, 'severity': severity, 'field': field})
    kinds = {d['kind'] for d in app['documents']}
    for kind, label in REQUIRED_DOCS.items():
        if kind not in kinds:
            issue('missing_' + kind, f'Upload your {label.lower()}.', 'C1')
    fields = app['fields']
    for doc in app['documents']:
        extracted = {v['key'] for v in doc['extracted']}
        for key in EXPECTED[doc['kind']]:
            if key not in extracted and not fields[key]['confirmed']:
                issue(f"unreadable_{doc['id']}_{key}", f"Verify {FIELDS[key].lower()} missing from {doc['name']}.", 'C2' if key == 'full_name' else 'C4', field=key)
    for key in REQUIRED_FIELDS:
        f = fields[key]
        if not f['value']:
            issue('field_' + key, f'Provide {f["label"].lower()}.', 'C4', field=key)
        values = {str(s['value']).strip().casefold() for s in f['sources']}
        if len(values) > 1:
            if f['confirmed']:
                issue('resolved_' + key, f'{f["label"]} differs between documents; your confirmed value will be used. Original evidence is retained for reviewer attention.', 'C2', 'warning', key)
            else:
                issue('conflict_' + key, f'{f["label"]} differs between documents. Compare the sources and confirm the correct value.', 'C2' if key in ['full_name', 'policy_number', 'hospital_name'] else 'C3', field=key)
    value = lambda key: fields[key]['value']
    policy_number = app['issued_policy']['number'] if app.get('issued_policy') else POLICY_NUMBER
    if value('policy_number') and value('policy_number') != policy_number:
        issue('unsupported_policy', 'This POC only supports synthetic policy POC-2026-001. This uploaded policy cannot be verified.', 'C2', field='policy_number')
    dates = {}
    for key in ['admission_date', 'discharge_date', 'policy_start', 'policy_end']:
        if value(key):
            try:
                dates[key] = date.fromisoformat(value(key))
            except ValueError:
                issue('invalid_' + key, f'{FIELDS[key]} must be a valid date in YYYY-MM-DD format.', 'C3', field=key)
    if dates.get('admission_date') and dates.get('discharge_date') and dates['admission_date'] > dates['discharge_date']:
        issue('date_order', 'Admission date must be on or before discharge date.', 'C3', field='admission_date')
    if dates.get('policy_start') and dates.get('policy_end') and dates['policy_start'] > dates['policy_end']:
        issue('policy_order', 'Policy start must be on or before policy end.', 'C3', field='policy_start')
    for key in ['admission_date', 'discharge_date']:
        if all(k in dates for k in [key, 'policy_start', 'policy_end']) and not dates['policy_start'] <= dates[key] <= dates['policy_end']:
            issue('outside_' + key, f'{FIELDS[key]} falls outside the policy period. Insurer review is required.', 'C3', field=key)
    if value('bill_total'):
        try:
            amount = Decimal(value('bill_total').replace(',', ''))
            if not amount.is_finite() or amount <= 0:
                raise InvalidOperation
            if amount > (app.get('issued_policy') or {}).get('sum_insured', 500000):
                issue('over_limit', 'The bill exceeds the synthetic sum insured of INR 500000. Manual insurer review is required.', 'C4', field='bill_total')
        except InvalidOperation:
            issue('invalid_amount', 'Hospital bill total must be a positive INR amount.', 'C4', field='bill_total')
    if value('bank_account_last4') and (len(value('bank_account_last4')) != 4 or not value('bank_account_last4').isascii() or not value('bank_account_last4').isdigit()):
        issue('invalid_bank', 'Enter exactly four digits for the bank account suffix.', 'C4', field='bank_account_last4')
    app['issues'] = issues
    app['eligibility'] = assess(app)
    return {'application': app}


def status(state):
    app = state['application']
    blockers = [i for i in app['issues'] if i['severity'] == 'error']
    filled = sum(bool(app['fields'][k]['value']) for k in REQUIRED_FIELDS)
    docs = len({d['kind'] for d in app['documents']})
    app['progress'] = min(90, round((filled + docs) / (len(REQUIRED_FIELDS) + 4) * 90))
    app['status'] = 'collecting' if docs < 4 else 'needs_attention' if blockers else 'review'
    if blockers and docs == 4:
        app['progress'] = min(app['progress'], 80)
    if not blockers and app.get('reviewed_at'):
        app['status'] = 'ready'
        app['progress'] = 100
    return {'application': app}


builder = StateGraph(WorkflowState)
builder.add_node('assemble', assemble)
builder.add_node('validate', validate)
builder.add_node('status', status)
builder.add_edge(START, 'assemble')
builder.add_edge('assemble', 'validate')
builder.add_edge('validate', 'status')
builder.add_edge('status', END)
graph = builder.compile()


def run(app):
    if app.get('journey') == 'cashless':
        from .cashless import check
        # Keep a field view for provenance, while using a separate pre-admission workflow.
        app = assemble({'application': app})['application']
        return check(app)
    return graph.invoke({'application': app})['application']
