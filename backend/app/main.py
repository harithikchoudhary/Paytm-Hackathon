import logging
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from .config import settings
from .models import CreateApplication, Correction, Message, DemoRequest, DocumentKind, FIELDS, CashlessDetails, SimulationAction
from . import store, providers
from .workflow import run
from .policies import CLAUSES, POLICY_ID, retrieve
from .samples import sample, policy_pdf, LABELS, issued_schedule, pdf_bytes
from .export import packet
from .customer import ISSUED_POLICY, HOSPITALS, issued_policy, policy_context
from . import cashless

logger = logging.getLogger('oneflow')
app = FastAPI(title='OneFlow AI', version='0.2.0', description='Existing-policy reimbursement and simulated cashless assistance POC')
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'], allow_headers=['Content-Type'])


def load(app_id):
    record = store.get(app_id)
    if not record:
        raise HTTPException(404, 'Application not found.')
    return record


def public(record):
    return {**record, 'policy_context': policy_context(record), 'documents': [{k: v for k, v in d.items() if k not in ['path', 'pages']} for d in record['documents']]}


def check_cloud():
    if settings.oneflow_mode == 'cloud' and settings.cloud_missing():
        raise HTTPException(503, 'Cloud configuration missing: ' + ', '.join(settings.cloud_missing()))


def process_document(record, content, name, kind, mime):
    check_cloud()
    pages = providers.read_pages(content, mime)
    extracted = providers.extract(pages, kind)
    doc_id = str(uuid4())
    directory = settings.oneflow_data_dir / 'uploads' / record['id']
    directory.mkdir(parents=True, exist_ok=True)
    suffix = {'application/pdf': '.pdf', 'image/png': '.png', 'image/jpeg': '.jpg'}[mime]
    path = directory / (doc_id + suffix)
    path.write_bytes(content)
    previous = [d for d in record['documents'] if d['kind'] == kind]
    record['documents'] = [d for d in record['documents'] if d['kind'] != kind]
    # Replacing a source invalidates related manual confirmations.
    related_keys = {f['key'] for d in previous for f in d['extracted']} | {f['key'] for f in extracted}
    for key in related_keys:
        record['corrections'].pop(key, None)
    record['documents'].append({'id': doc_id, 'name': Path(name.replace('\\', '/')).name[:160],
        'kind': kind, 'mime': mime, 'size': len(content), 'page_count': len(pages),
        'path': str(path), 'pages': pages, 'extracted': extracted,
        'provider': 'Document AI + Vertex AI' if settings.oneflow_mode == 'cloud' else 'Demo parser', 'uploaded_at': store.now()})
    cashless.invalidate(record)
    store.mutate(record, 'document_uploaded', {'kind': kind, 'name': name, 'replaced': [d['id'] for d in previous]})
    result = store.save(run(record))
    for old in previous:
        Path(old['path']).unlink(missing_ok=True)
    return result


@app.get('/api/health')
def health():
    return {'status': 'ok', 'mode': settings.oneflow_mode, 'cloud_configured': not settings.cloud_missing(),
            'missing_configuration': settings.cloud_missing(), 'model': settings.vertex_model,
            'policy_id': POLICY_ID, 'synthetic_only': True, 'cashless_simulator': True, 'existing_policy_journeys': True}


@app.get('/api/policy')
def policy(application_id: str | None = None):
    return policy_context(load(application_id) if application_id else {})


@app.get('/api/customer/policies')
def customer_policies():
    return {'customer': {'name': 'Aarav Sharma', 'is_demo': True}, 'policies': [ISSUED_POLICY], 'live_integration': False}


@app.get('/api/hospitals')
def hospitals(q: str = ''):
    return {'hospitals': [h for h in HOSPITALS if q.casefold() in (h['name'] + ' ' + h['city'] + ' ' + h['area']).casefold()],
            'is_demo': True, 'notice': 'Fictional directory. Network arrangements are simulated, not verified with an insurer.'}


@app.get('/api/policy/checklist')
def checklist_source():
    context = policy_context({'issued_policy': ISSUED_POLICY})
    lines = [c['section'] + ': ' + c['text'] for c in context['clauses'] if c['id'].startswith('P')]
    return Response(pdf_bytes('OneFlow POC preparation checks', lines), media_type='application/pdf')


@app.get('/api/policy/pdf')
def policy_download():
    return Response(policy_pdf(), media_type='application/pdf', headers={'Content-Disposition': 'inline; filename="synthetic-policy.pdf"'})


@app.get('/api/samples/{kind}')
def sample_download(kind: DocumentKind):
    return Response(sample(kind), media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="sample-{kind}.pdf"'})


@app.get('/api/applications')
def applications():
    return [{'id': a['id'], 'title': a['title'], 'status': a['status'], 'progress': a['progress'], 'journey': a.get('journey', 'reimbursement'), 'updated_at': a['updated_at']} for a in store.all_applications()]


@app.post('/api/applications', status_code=201)
def create(body: CreateApplication):
    policy = issued_policy(body.issued_policy_id) if body.issued_policy_id else None
    if body.issued_policy_id and not policy:
        raise HTTPException(404, 'Customer policy not found.')
    if body.journey == 'cashless' and not policy:
        raise HTTPException(422, 'Select an existing customer policy for cashless assistance.')
    if policy and body.member_id not in {m['id'] for m in policy['members']}:
        raise HTTPException(422, 'Select an insured member on this policy.')
    record = store.create(body.title, body.journey, policy, body.member_id)
    if policy:
        content, extracted = issued_schedule(policy, body.member_id)
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
def get_application(app_id: str):
    return public(run(load(app_id)))


@app.post('/api/applications/{app_id}/documents')
def upload(app_id: str, kind: DocumentKind = Form(...), file: UploadFile = File(...)):
    record = load(app_id)
    if record.get('issued_policy') and kind == 'policy':
        raise HTTPException(409, 'Your existing policy is preloaded. Start a new journey to select a different policy or member.')
    if record.get('journey') == 'cashless' and kind not in ('admission_advice', 'cost_estimate'):
        raise HTTPException(422, 'Cashless preparation accepts admission advice and a cost estimate. Reimbursement uses a separate journey.')
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
        return public(process_document(record, content, file.filename or 'document', kind, mime))
    except HTTPException:
        raise
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        logger.exception('Document processing failed')
        raise HTTPException(502, 'Document processing failed. Check Google Cloud credentials, processor location, API access, and document readability. Your existing progress is preserved.') from error


@app.delete('/api/applications/{app_id}/documents/{doc_id}')
def remove_document(app_id: str, doc_id: str):
    record = load(app_id)
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
def original_document(app_id: str, doc_id: str):
    doc = next((d for d in load(app_id)['documents'] if d['id'] == doc_id), None)
    if not doc:
        raise HTTPException(404, 'Document not found.')
    return FileResponse(doc['path'], media_type=doc['mime'], filename=doc['name'], content_disposition_type='inline')


@app.patch('/api/applications/{app_id}/fields/{key}')
def correct(app_id: str, key: str, body: Correction):
    if key not in FIELDS:
        raise HTTPException(422, 'Unknown field.')
    if not body.value.strip():
        raise HTTPException(422, 'Value cannot be blank.')
    record = load(app_id)
    if record.get('journey') == 'cashless':
        raise HTTPException(409, 'Update admission details or replace clinical evidence in the cashless journey.')
    if record.get('issued_policy') and key in ('full_name', 'policy_number', 'policy_start', 'policy_end'):
        raise HTTPException(409, 'This value comes from the existing issued schedule. Select the correct member in a new journey or replace a conflicting claim document.')
    record['corrections'][key] = body.value.strip()
    store.mutate(record, 'field_confirmed', {'field': key, 'value': body.value.strip()})
    return public(store.save(run(record)))


@app.post('/api/applications/{app_id}/review')
def review(app_id: str):
    record = run(load(app_id))
    if record.get('journey') == 'cashless':
        raise HTTPException(409, 'Use the cashless preparation and simulation controls for this journey.')
    if any(i['severity'] == 'error' for i in record['issues']):
        raise HTTPException(409, 'Resolve all blocking issues before confirming your review.')
    record['reviewed_at'] = store.now()
    record['audit'].append({'at': store.now(), 'event': 'review_confirmed', 'details': {'revision': record['revision']}})
    return public(store.save(run(record)))


@app.post('/api/applications/{app_id}/messages')
def message(app_id: str, body: Message):
    check_cloud()
    record = load(app_id)
    clauses = retrieve(body.text, corpus=policy_context(record)['clauses'])
    try:
        answer = providers.explain(body.text, clauses, {'issues': record['issues'], 'status': record['status'],
            'journey': record.get('journey', 'reimbursement'), 'cashless': record.get('cashless'),
            'fields': {k: v['value'] for k, v in record['fields'].items()}})
    except Exception as error:
        logger.exception('Vertex AI explanation failed')
        raise HTTPException(502, 'Vertex AI is unavailable. Your application is saved; please retry or read the policy directly.') from error
    used = [c for c in clauses if c['id'] in answer['clause_ids']]
    record['messages'].extend([
        {'id': str(uuid4()), 'role': 'user', 'text': body.text, 'at': store.now(), 'citations': []},
        {'id': str(uuid4()), 'role': 'assistant', 'text': answer['answer'], 'at': store.now(), 'citations': used},
    ])
    return public(store.save(record))


@app.post('/api/applications/{app_id}/demo')
def demo(app_id: str, body: DemoRequest):
    if settings.oneflow_mode != 'demo':
        raise HTTPException(409, 'Sample loading is available only in demo mode. Download the samples and upload them to exercise the cloud pipeline.')
    record = load(app_id)
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
def export(app_id: str):
    record = run(load(app_id))
    if record['status'] != 'ready':
        raise HTTPException(409, 'Complete validation and confirm your review before exporting.')
    return Response(packet(record), media_type='application/zip', headers={'Content-Disposition': f'attachment; filename="oneflow-claim-{app_id[:8]}.zip"'})


def load_cashless(app_id):
    record = load(app_id)
    if record.get('journey') != 'cashless':
        raise HTTPException(409, 'This application uses the reimbursement journey.')
    return record


@app.put('/api/applications/{app_id}/cashless/details')
def cashless_details(app_id: str, body: CashlessDetails):
    record = load_cashless(app_id)
    if body.member_id != record['member_id']:
        raise HTTPException(422, 'Patient must match the insured member selected for this journey. Start a new journey to change the patient.')
    if body.hospital_id not in {h['id'] for h in HOSPITALS}:
        raise HTTPException(422, 'Hospital not found in the sample directory.')
    cashless.invalidate(record)
    record['cashless']['details'] = body.model_dump()
    store.mutate(record, 'cashless_details_saved', {'simulation': True, 'hospital': body.hospital_id, 'admission_type': body.admission_type})
    return public(store.save(run(record)))


@app.post('/api/applications/{app_id}/cashless/simulate')
def cashless_simulate(app_id: str, body: SimulationAction):
    record = load_cashless(app_id)
    try:
        result = cashless.transition(record, body.action, body.clarification)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    return public(store.save(result))


@app.get('/api/applications/{app_id}/cashless/brief')
def cashless_brief(app_id: str):
    record = run(load_cashless(app_id))
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
