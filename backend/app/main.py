import logging
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from .config import settings
from .models import CreateApplication, Correction, Message, DemoRequest, DocumentKind, FIELDS, CashlessDetails, SimulationAction, SubmitClaim, InsurerAction, ClarificationResponse
from . import store, providers
from .workflow import run
from .policies import CLAUSES, POLICY_ID, retrieve
from .samples import sample, policy_pdf, LABELS, issued_schedule, pdf_bytes
from .export import packet
from .customer import ISSUED_POLICY, HOSPITALS, issued_policy, policy_context, customer_policy_document, POLICY_PDF_PATH
from . import cashless
from .insurer import simulated_insurer, utc_now

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
logger = logging.getLogger('oneflow')
app = FastAPI(title='OneFlow AI', version='0.2.0', description='Existing-policy reimbursement and simulated cashless assistance')
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'], allow_headers=['Content-Type', 'X-OneFlow-User'])


def current_user(x_oneflow_user: str | None = Header(default=None)):
    return (x_oneflow_user or 'demo-user').strip()[:120]


def load(app_id, user='demo-user'):
    record = store.get(app_id)
    if not record:
        raise HTTPException(404, 'Application not found.')
    if record.get('owner_id', 'demo-user') != user:
        raise HTTPException(404, 'Application not found.')
    return record


def public(record):
    claim = store.get_claim(record['id'])
    return {**record, 'claim': claim, 'insurer_events': store.insurer_events(record['id']), 'policy_context': policy_context(record), 'documents': [{k: v for k, v in d.items() if k not in ['path', 'pages']} for d in record['documents']]}


def check_cloud():
    if settings.oneflow_mode == 'cloud' and settings.cloud_missing():
        raise HTTPException(503, 'Cloud configuration missing: ' + ', '.join(settings.cloud_missing()))


def process_document(record, content, name, kind, mime, replace=False):
    check_cloud()
    pages = providers.read_pages(content, mime)
    extracted = providers.extract_with_content(pages, kind, content, name, mime)
    doc_id = str(uuid4())
    directory = settings.oneflow_data_dir / 'uploads' / record['id']
    directory.mkdir(parents=True, exist_ok=True)
    suffix = {'application/pdf': '.pdf', 'image/png': '.png', 'image/jpeg': '.jpg'}[mime]
    path = directory / (doc_id + suffix)
    path.write_bytes(content)
    previous = [d for d in record['documents'] if d['kind'] == kind]
    removed = previous if replace else []
    if replace:
        record['documents'] = [d for d in record['documents'] if d['kind'] != kind]
    # Replacing a source invalidates related manual confirmations.
    related_keys = {f['key'] for d in previous for f in d['extracted']} | {f['key'] for f in extracted}
    for key in related_keys:
        record['corrections'].pop(key, None)
    record['documents'].append({'id': doc_id, 'name': Path(name.replace('\\', '/')).name[:160],
        'kind': kind, 'mime': mime, 'size': len(content), 'page_count': len(pages),
        'path': str(path), 'pages': pages, 'extracted': extracted,
        'provider': ('Sarvam Vision + Sarvam Chat' if settings.ai_provider == 'sarvam' else 'Document AI + Vertex AI') if settings.oneflow_mode == 'cloud' else 'Demo parser', 'uploaded_at': store.now()})
    if not (record.get('journey') == 'cashless' and kind in ('bill', 'discharge') and (record.get('cashless') or {}).get('status') in ('authorized', 'discharge_review')):
        cashless.invalidate(record)
    store.mutate(record, 'document_uploaded', {'kind': kind, 'name': name, 'replaced': [d['id'] for d in removed], 'appended': not replace})
    result = run(record)
    active_claim = store.get_claim(record['id'])
    if active_claim:
        result['status'] = 'claim_' + active_claim['status']
    result = store.save(result)
    for old in removed:
        Path(old['path']).unlink(missing_ok=True)
    return result


@app.get('/api/health')
def health():
    active_model = settings.sarvam_chat_model if settings.ai_provider == 'sarvam' else settings.vertex_model
    return {'status': 'ok', 'mode': settings.oneflow_mode, 'cloud_configured': not settings.cloud_missing(),
            'missing_configuration': settings.cloud_missing(), 'provider': settings.ai_provider, 'model': active_model,
            'policy_id': POLICY_ID, 'synthetic_only': True, 'cashless_simulator': True, 'existing_policy_journeys': True}


@app.get('/api/auth/session')
def auth_session(user=Header(default='demo-user', alias='X-OneFlow-User')):
    return {'user_id': user or 'demo-user', 'authenticated': True, 'mode': 'demo authentication'}


@app.get('/api/policy')
def policy(application_id: str | None = None):
    return policy_context(load(application_id) if application_id else {})


@app.get('/api/customer/policies')
def customer_policies():
    return {'customer': {'name': '', 'is_demo': True}, 'policies': [], 'live_integration': False}


@app.get('/api/customer/profile')
def customer_profile(user=Header(default='demo-user', alias='X-OneFlow-User')):
    return {'profile': {'id': user or 'demo-user', 'name': '', 'email': '', 'mobile': '', 'address': '',
                        'kyc_status': 'Not added', 'notice': 'Add your own details and policy documents for this local demo.'},
            'policies': [], 'live_integration': False}


@app.get('/api/customer/policies/{policy_id}/file')
def customer_policy_file(policy_id: str):
    if policy_id != ISSUED_POLICY['id'] or not POLICY_PDF_PATH.exists():
        raise HTTPException(404, 'Customer policy not found.')
    return FileResponse(POLICY_PDF_PATH, media_type='application/pdf', filename='01_OneFlow_Health_Policy.pdf', content_disposition_type='inline')


@app.get('/api/hospitals')
def hospitals(q: str = ''):
    return {'hospitals': [h for h in HOSPITALS if q.casefold() in (h['name'] + ' ' + h['city'] + ' ' + h['area']).casefold()],
            'is_demo': True, 'notice': 'Fictional directory. Network arrangements are simulated, not verified with an insurer.'}


@app.get('/api/policy/checklist')
def checklist_source():
    context = policy_context({'issued_policy': ISSUED_POLICY})
    lines = [c['section'] + ': ' + c['text'] for c in context['clauses'] if c['id'].startswith('P')]
    return Response(pdf_bytes('OneFlow claim preparation checks', lines), media_type='application/pdf')


@app.get('/api/policy/pdf')
def policy_download():
    return Response(policy_pdf(), media_type='application/pdf', headers={'Content-Disposition': 'inline; filename="synthetic-policy.pdf"'})


@app.get('/api/samples/{kind}')
def sample_download(kind: DocumentKind):
    return Response(sample(kind), media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="sample-{kind}.pdf"'})


@app.get('/api/applications')
def applications(user=Header(default='demo-user', alias='X-OneFlow-User')):
    return [{'id': a['id'], 'title': a['title'], 'status': a['status'], 'progress': a['progress'], 'journey': a.get('journey', 'reimbursement'), 'updated_at': a['updated_at']} for a in store.all_applications() if a.get('owner_id', 'demo-user') == (user or 'demo-user')]


@app.post('/api/applications', status_code=201)
def create(body: CreateApplication, user=Header(default='demo-user', alias='X-OneFlow-User')):
    policy = issued_policy(body.issued_policy_id) if body.issued_policy_id else body.issued_policy
    if body.issued_policy_id and not policy:
        raise HTTPException(404, 'Customer policy not found.')
    if body.journey == 'cashless' and not policy:
        raise HTTPException(422, 'Select an existing customer policy for cashless assistance.')
    if policy and body.member_id not in {m['id'] for m in policy['members']}:
        raise HTTPException(422, 'Select an insured member on this policy.')
    owner = user or 'demo-user'
    record = store.create(body.title, body.journey, policy, body.member_id, owner)
    if policy:
        content, extracted = customer_policy_document(policy, body.member_id) if policy['id'] == ISSUED_POLICY['id'] else issued_schedule(policy, body.member_id)
        doc_id = str(uuid4())
        directory = settings.oneflow_data_dir / 'uploads' / record['id']
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (doc_id + '.pdf')
        path.write_bytes(content)
        record['documents'].append({'id': doc_id, 'name': 'existing-policy-schedule-demo.pdf', 'kind': 'policy',
            'mime': 'application/pdf', 'size': len(content), 'page_count': 1, 'path': str(path), 'pages': [],
            'extracted': extracted, 'provider': 'Existing customer policy — fictional fixture', 'uploaded_at': store.now(), 'preloaded': True})
        store.mutate(record, 'existing_policy_loaded', {'policy': policy['number'], 'member': body.member_id, 'fictional': True})
    return public(store.save(run(record)))


@app.get('/api/applications/{app_id}')
def get_application(app_id: str, user=Header(default='demo-user', alias='X-OneFlow-User')):
    return public(run(load(app_id, user or 'demo-user')))


@app.post('/api/applications/{app_id}/documents')
def upload(app_id: str, kind: DocumentKind = Form(...), file: UploadFile = File(...), replace: bool = Form(True), user=Header(default='demo-user', alias='X-OneFlow-User')):
    record = load(app_id, user or 'demo-user')
    if record.get('issued_policy') and kind == 'policy':
        raise HTTPException(409, 'Your existing policy is preloaded. Start a new journey to select a different policy or member.')
    claim = store.get_claim(app_id)
    if kind == 'clarification' and (not claim or claim.get('status') != 'clarification_requested'):
        raise HTTPException(409, 'Clarification uploads are available only after the simulated insurer requests information.')
    if record.get('journey') == 'cashless' and kind not in ('admission_advice', 'cost_estimate', 'bill', 'discharge'):
        raise HTTPException(422, 'Cashless preparation accepts admission evidence, a cost estimate, and final bill/discharge evidence.')
    if record.get('journey') == 'cashless' and kind in ('bill', 'discharge') and (record.get('cashless') or {}).get('status') not in ('authorized', 'discharge_review'):
        raise HTTPException(409, 'Final bill and discharge evidence can be uploaded after simulated authorization.')
    if record.get('journey') != 'cashless' and kind in ('admission_advice', 'cost_estimate'):
        raise HTTPException(422, 'Use the cashless assistance journey for pre-admission documents.')
    content = file.file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, 'Maximum upload size is 10 MB.')
    if content.startswith(b'%PDF-'):
        mime = 'application/pdf'
    elif content.startswith(b'\x89PNG\r\n\x1a\n'):
        mime = 'image/png'
    elif content.startswith(b'\xff\xd8\xff'):
        mime = 'image/jpeg'
    else:
        raise HTTPException(415, 'Upload a valid PDF, PNG, or JPEG document.')
    try:
        return public(process_document(record, content, file.filename or 'document', kind, mime, replace=replace))
    except HTTPException:
        raise
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        logger.exception('Document processing failed')
        if settings.ai_provider == 'sarvam':
            message = 'Sarvam could not read this document. Check the API key, file quality, supported format, and Sarvam account access. Your existing progress is preserved.'
        else:
            message = 'Document processing failed. Check Google Cloud credentials, processor location, API access, and document readability. Your existing progress is preserved.'
        raise HTTPException(502, message) from error


@app.delete('/api/applications/{app_id}/documents/{doc_id}')
def remove_document(app_id: str, doc_id: str, user=Header(default='demo-user', alias='X-OneFlow-User')):
    record = load(app_id, user or 'demo-user')
    claim = store.get_claim(app_id)
    if claim and claim.get('status') not in ('clarification_requested',):
        raise HTTPException(409, 'Submitted claim documents are locked. Use a clarification request to add evidence.')
    doc = next((d for d in record['documents'] if d['id'] == doc_id), None)
    if not doc:
        raise HTTPException(404, 'Document not found.')
    if doc.get('preloaded'):
        raise HTTPException(409, 'The existing customer policy cannot be removed from this journey.')
    record['documents'] = [d for d in record['documents'] if d['id'] != doc_id]
    for field in doc['extracted']:
        record['corrections'].pop(field['key'], None)
    store.mutate(record, 'document_removed', {'id': doc_id, 'kind': doc['kind']})
    cashless.invalidate(record)
    result = store.save(run(record))
    Path(doc['path']).unlink(missing_ok=True)
    return public(result)


@app.get('/api/applications/{app_id}/documents/{doc_id}/file')
def original_document(app_id: str, doc_id: str, user=Header(default='demo-user', alias='X-OneFlow-User')):
    doc = next((d for d in load(app_id, user or 'demo-user')['documents'] if d['id'] == doc_id), None)
    if not doc:
        raise HTTPException(404, 'Document not found.')
    return FileResponse(doc['path'], media_type=doc['mime'], filename=doc['name'], content_disposition_type='inline')


@app.patch('/api/applications/{app_id}/fields/{key}')
def correct(app_id: str, key: str, body: Correction, user=Header(default='demo-user', alias='X-OneFlow-User')):
    if key not in FIELDS:
        raise HTTPException(422, 'Unknown field.')
    if not body.value.strip():
        raise HTTPException(422, 'Value cannot be blank.')
    record = load(app_id, user or 'demo-user')
    if (claim := store.get_claim(app_id)) and claim.get('status') not in ('clarification_requested',):
        raise HTTPException(409, 'Submitted claim details are locked. Respond to a clarification request instead.')
    if record.get('journey') == 'cashless':
        raise HTTPException(409, 'Update admission details or replace clinical evidence in the cashless journey.')
    if record.get('issued_policy') and key in ('full_name', 'policy_number', 'policy_start', 'policy_end'):
        raise HTTPException(409, 'This value comes from the existing issued schedule. Select the correct member in a new journey or replace a conflicting claim document.')
    record['corrections'][key] = body.value.strip()
    store.mutate(record, 'field_confirmed', {'field': key, 'value': body.value.strip()})
    return public(store.save(run(record)))


@app.post('/api/applications/{app_id}/review')
def review(app_id: str, user=Header(default='demo-user', alias='X-OneFlow-User')):
    record = run(load(app_id, user or 'demo-user'))
    if record.get('journey') == 'cashless':
        raise HTTPException(409, 'Use the cashless preparation and simulation controls for this journey.')
    if any(i['severity'] == 'error' for i in record['issues']):
        raise HTTPException(409, 'Resolve all blocking issues before confirming your review.')
    record['reviewed_at'] = store.now()
    record['audit'].append({'at': store.now(), 'event': 'review_confirmed', 'details': {'revision': record['revision']}})
    return public(store.save(run(record)))


@app.post('/api/applications/{app_id}/messages')
def message(app_id: str, body: Message, user=Header(default='demo-user', alias='X-OneFlow-User')):
    check_cloud()
    record = load(app_id, user or 'demo-user')
    clauses = retrieve(body.text, corpus=policy_context(record)['clauses'])
    try:
        answer = providers.explain(body.text, clauses, {'issues': record['issues'], 'status': record['status'],
            'journey': record.get('journey', 'reimbursement'), 'cashless': record.get('cashless'),
            'fields': {k: v['value'] for k, v in record['fields'].items()}})
    except Exception as error:
        logger.exception('%s explanation failed', settings.ai_provider)
        provider_name = 'Sarvam AI' if settings.ai_provider == 'sarvam' else 'Vertex AI'
        raise HTTPException(502, f'{provider_name} is unavailable. Your application is saved; please retry or read the policy directly.') from error
    used = [c for c in clauses if c['id'] in answer['clause_ids']]
    record['messages'].extend([
        {'id': str(uuid4()), 'role': 'user', 'text': body.text, 'at': store.now(), 'citations': []},
        {'id': str(uuid4()), 'role': 'assistant', 'text': answer['answer'], 'at': store.now(), 'citations': used},
    ])
    return public(store.save(record))


@app.post('/api/applications/{app_id}/demo')
def demo(app_id: str, body: DemoRequest, user=Header(default='demo-user', alias='X-OneFlow-User')):
    if settings.oneflow_mode != 'demo':
        raise HTTPException(409, 'Sample loading is available only in demo mode. Download the samples and upload them to exercise the cloud pipeline.')
    record = load(app_id, user or 'demo-user')
    if record['documents'] or record['corrections']:
        raise HTTPException(409, 'Start a new application before loading a sample case.')
    if record.get('journey') == 'cashless' or record.get('issued_policy'):
        raise HTTPException(409, 'Create a fresh legacy sample application or use downloaded claim samples with your existing policy.')
    for kind in ('policy', 'bill', 'discharge', 'bank_proof'):
        if kind == 'bank_proof' and body.scenario == 'missing':
            continue
        record = process_document(record, sample(kind, conflict=body.scenario == 'conflict'), f'sample-{kind}.pdf', kind, 'application/pdf')
    record['messages'].append({'id': str(uuid4()), 'role': 'assistant', 'at': store.now(), 'citations': [CLAUSES[0]],
        'text': 'I have checked your synthetic documents. ' + ('Your bank account proof is missing. Upload it to complete the document checklist.' if body.scenario == 'missing' else 'The patient name differs between your bill and policy. Compare both sources in Review details.' if body.scenario == 'conflict' else 'All required documents and fields are present. Review the details, then confirm to prepare your packet.')})
    return public(store.save(record))


@app.get('/api/applications/{app_id}/export')
def export(app_id: str, user=Header(default='demo-user', alias='X-OneFlow-User')):
    record = run(load(app_id, user or 'demo-user'))
    if record['status'] != 'ready':
        raise HTTPException(409, 'Complete validation and confirm your review before exporting.')
    if not record.get('packet_generated_at'):
        record['packet_generated_at'] = utc_now()
        record['revision'] += 1
        record['audit'].append({'at': utc_now(), 'event': 'claim_packet_generated', 'details': {'simulation': True}})
        store.save(record)
    return Response(packet(record), media_type='application/zip', headers={'Content-Disposition': f'attachment; filename="oneflow-claim-{app_id[:8]}.zip"'})


@app.post('/api/applications/{app_id}/submit', status_code=201)
def submit_claim(app_id: str, body: SubmitClaim, user=Header(default='demo-user', alias='X-OneFlow-User')):
    record = load(app_id, user or 'demo-user')
    if record.get('journey') == 'cashless':
        raise HTTPException(409, 'Cashless claims use the preauthorization flow.')
    if not body.consent:
        raise HTTPException(422, 'Explicit consent is required before simulated submission.')
    existing = store.get_claim(app_id)
    if existing:
        raise HTTPException(409, 'This claim has already been submitted. Use tracking for its current status.')
    record = run(record)
    if record['status'] != 'ready' or not record.get('packet_generated_at'):
        raise HTTPException(409, 'Confirm the review and download the claim packet before submitting.')
    amount = record['fields'].get('bill_total', {}).get('value', '0').replace(',', '') or '0'
    claim = {'application_id': app_id, 'claim_id': 'CLM-' + uuid4().hex[:12].upper(), 'status': 'draft',
             'submitted_at': None, 'updated_at': utc_now(), 'claim_amount': amount,
             'approved_amount': None, 'explanation': '', 'settlement': None, 'timeline': [],
             'packet_generated_at': record.get('packet_generated_at'), 'document_count': len(record['documents']),
             'claim_details': record.get('claim_details', {})}
    claim = simulated_insurer.submit(record, claim)
    record['status'] = 'submitted'
    store.mutate(record, 'claim_submitted', {'claim_id': claim['claim_id'], 'acknowledgement_id': claim['acknowledgement_id'], 'simulation': True})
    store.save(record)
    return public(record)


@app.get('/api/applications/{app_id}/claim')
def claim_tracking(app_id: str, user=Header(default='demo-user', alias='X-OneFlow-User')):
    record = load(app_id, user or 'demo-user')
    claim = store.get_claim(app_id)
    if not claim:
        raise HTTPException(404, 'No submitted claim exists for this application.')
    return {'claim': claim, 'timeline': store.insurer_events(app_id), 'application': {'id': app_id, 'title': record['title'], 'status': record['status']}}


@app.post('/api/applications/{app_id}/claim/clarification')
def submit_clarification(app_id: str, body: ClarificationResponse, user=Header(default='demo-user', alias='X-OneFlow-User')):
    record = load(app_id, user or 'demo-user')
    claim = store.get_claim(app_id)
    if not claim or claim.get('status') != 'clarification_requested':
        raise HTTPException(409, 'The simulated insurer has not requested clarification.')
    claim = simulated_insurer.event(record, claim, 'resubmit', {'explanation': body.response})
    record['status'] = 'claim_resubmitted'
    store.mutate(record, 'claim_clarification_resubmitted', {'claim_id': claim['claim_id'], 'simulation': True})
    store.save(record)
    return public(record)


@app.post('/api/applications/{app_id}/claim/admin-action')
def insurer_admin_action(app_id: str, body: InsurerAction, x_oneflow_admin: str | None = Header(default=None), user=Header(default='demo-user', alias='X-OneFlow-User')):
    if x_oneflow_admin != 'simulator-admin':
        raise HTTPException(403, 'Simulator admin credentials are required.')
    record = load(app_id, user or 'demo-user')
    claim = store.get_claim(app_id)
    if not claim:
        raise HTTPException(404, 'No submitted claim exists for this application.')
    if body.action == 'request_information' and claim['status'] not in ('submitted', 'resubmitted'):
        raise HTTPException(409, 'Information can only be requested while the claim is under review.')
    if body.action in ('approve', 'partial_approve', 'reject') and claim['status'] not in ('submitted', 'resubmitted'):
        raise HTTPException(409, 'A decision is not available in the current claim status.')
    if body.action == 'settle' and claim['status'] not in ('approved', 'partially_approved'):
        raise HTTPException(409, 'Settlement requires an approval decision.')
    payload = {'explanation': body.explanation} if body.explanation else {}
    if body.approved_amount is not None:
        payload['approved_amount'] = body.approved_amount
    claim = simulated_insurer.event(record, claim, body.action, payload)
    record['status'] = 'claim_' + claim['status']
    store.mutate(record, 'insurer_' + claim['status'], {'claim_id': claim['claim_id'], 'simulation': True})
    store.save(record)
    return public(record)


def load_cashless(app_id, user='demo-user'):
    record = load(app_id, user)
    if record.get('journey') != 'cashless':
        raise HTTPException(409, 'This application uses the reimbursement journey.')
    return record


@app.put('/api/applications/{app_id}/cashless/details')
def cashless_details(app_id: str, body: CashlessDetails, user=Header(default='demo-user', alias='X-OneFlow-User')):
    record = load_cashless(app_id, user or 'demo-user')
    if body.member_id != record['member_id']:
        raise HTTPException(422, 'Patient must match the insured member selected for this journey. Start a new journey to change the patient.')
    if body.hospital_id not in {h['id'] for h in HOSPITALS}:
        raise HTTPException(422, 'Hospital not found in the sample directory.')
    cashless.invalidate(record)
    record['cashless']['details'] = body.model_dump()
    store.mutate(record, 'cashless_details_saved', {'simulation': True, 'hospital': body.hospital_id, 'admission_type': body.admission_type})
    return public(store.save(run(record)))


@app.post('/api/applications/{app_id}/cashless/simulate')
def cashless_simulate(app_id: str, body: SimulationAction, user=Header(default='demo-user', alias='X-OneFlow-User')):
    record = load_cashless(app_id, user or 'demo-user')
    try:
        if body.action == 'submit' and not store.get_claim(app_id):
            estimate = record.get('cashless', {}).get('details', {}).get('estimated_amount', '0')
            preauth = {'application_id': app_id, 'claim_id': 'PREAUTH-' + uuid4().hex[:12].upper(), 'status': 'draft',
                       'submitted_at': None, 'updated_at': utc_now(), 'claim_amount': estimate,
                       'approved_amount': None, 'explanation': '', 'settlement': None, 'timeline': []}
            simulated_insurer.preauthorize(record, preauth)
        result = cashless.transition(record, body.action, body.clarification)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    claim = store.get_claim(app_id)
    if claim:
        state_map = {'authorized': 'authorized', 'declined': 'rejected', 'settled': 'settled'}
        target = state_map.get(result['cashless']['status'])
        if target and claim['status'] != target:
            claim['status'] = target
            claim['updated_at'] = utc_now()
            if target == 'authorized':
                claim['approved_amount'] = result['cashless'].get('authorized_amount')
            if target == 'settled':
                claim['settlement'] = {'settled_at': utc_now(), 'settled_amount': claim.get('approved_amount') or '0.00', 'reference': 'SIM-SET-' + uuid4().hex[:10].upper()}
            event = {'at': utc_now(), 'status': target, 'source': 'simulated_insurer', 'message': 'Simulated cashless status updated from the shared insurer adapter.'}
            claim.setdefault('timeline', []).append(event)
            store.save_claim(claim); store.add_insurer_event(app_id, event)
    return public(store.save(result))


@app.get('/api/applications/{app_id}/cashless/brief')
def cashless_brief(app_id: str, user=Header(default='demo-user', alias='X-OneFlow-User')):
    record = run(load_cashless(app_id, user or 'demo-user'))
    if record['issues']:
        raise HTTPException(409, 'Complete the preparation checklist before exporting the hospital handoff brief.')
    state = record['cashless']
    lines = ['SIMULATION ONLY - NO INSURER / TPA REQUEST SENT',
        f"Fictional policy: {record['issued_policy']['number']}", f"Patient: {record['fields']['full_name']['value']}",
        f"Hospital: {state['hospital']['name']} (fictional directory)",
        *[f'{k}: {v}' for k, v in state['details'].items()],
        'Status: simulated ' + state['status'], 'Any displayed authorized amount is an illustrative simulator value.',
        'The hospital insurance desk and insurer must confirm actual arrangements, required evidence, authorization and payment.']
    return Response(pdf_bytes('Cashless hospital handoff brief', lines), media_type='application/pdf',
        headers={'Content-Disposition': 'attachment; filename="cashless-handoff-simulation.pdf"'})


# The production frontend is served by the same backend when built.
dist = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
if dist.exists():
    app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')

    @app.get('/{path:path}', include_in_schema=False)
    def spa(path: str):
        if path.startswith('api/') or path == 'api':
            raise HTTPException(404, 'API route not found.')
        if path == 'favicon.svg':
            return FileResponse(dist / 'favicon.svg', media_type='image/svg+xml')
        return FileResponse(dist / 'index.html')
