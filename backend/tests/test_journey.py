import json
from io import BytesIO
from zipfile import ZipFile
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app import providers
from app.samples import sample, pdf_bytes


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'oneflow_data_dir', tmp_path)
    monkeypatch.setattr(settings, 'oneflow_mode', 'demo')
    with TestClient(app) as client:
        yield client


def new(client):
    r = client.post('/api/applications', json={'title': 'Test claim'})
    assert r.status_code == 201
    return r.json()['id']


def upload(client, app_id, kind, content=None):
    return client.post(f'/api/applications/{app_id}/documents', data={'kind': kind},
                       files={'file': (kind + '.pdf', content if content is not None else sample(kind), 'application/pdf')})


def demo(client, scenario):
    app_id = new(client)
    response = client.post(f'/api/applications/{app_id}/demo', json={'scenario': scenario})
    assert response.status_code == 200, response.text
    return app_id, response.json()


def test_complete_journey_review_and_packet(client):
    app_id, record = demo(client, 'complete')
    assert record['status'] == 'review'
    assert record['issues'] == []
    assert record['fields']['bill_total']['value'] == '48500'
    assert record['fields']['full_name']['sources'][0]['page'] == 1
    assert all('path' not in d and 'pages' not in d for d in record['documents'])
    assert client.get(f'/api/applications/{app_id}/export').status_code == 409
    reviewed = client.post(f'/api/applications/{app_id}/review').json()
    assert reviewed['status'] == 'ready'
    assert reviewed['progress'] == 100
    response = client.get(f'/api/applications/{app_id}/export')
    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as z:
        assert 'claim-summary.pdf' in z.namelist()
        assert len([n for n in z.namelist() if n.startswith('documents/')]) == 4
        data = json.loads(z.read('claim-data.json'))
        assert data['reviewed_at']
        assert data['fields']['full_name']['sources']
    # Reload retains the exact reviewed application.
    assert client.get(f'/api/applications/{app_id}').json()['status'] == 'ready'


def test_missing_document_recovery_and_review_invalidation(client):
    app_id, record = demo(client, 'missing')
    assert any(i['code'] == 'missing_bank_proof' for i in record['issues'])
    assert client.post(f'/api/applications/{app_id}/review').status_code == 409
    assert upload(client, app_id, 'bank_proof').json()['status'] == 'review'
    assert client.post(f'/api/applications/{app_id}/review').json()['status'] == 'ready'
    result = client.patch(f'/api/applications/{app_id}/fields/bill_total', json={'value': '48501'}).json()
    assert result['reviewed_at'] is None
    assert result['status'] == 'review'
    assert client.get(f'/api/applications/{app_id}/export').status_code == 409


def test_conflicting_name_confirmed_with_retained_evidence(client):
    app_id, record = demo(client, 'conflict')
    assert any(i['code'] == 'conflict_full_name' for i in record['issues'])
    result = client.patch(f'/api/applications/{app_id}/fields/full_name', json={'value': 'Aarav Sharma'}).json()
    assert result['status'] == 'review'
    assert any(i['code'] == 'resolved_full_name' and i['severity'] == 'warning' for i in result['issues'])
    assert len({s['value'] for s in result['fields']['full_name']['sources']}) == 2
    # Replacement resets confirmations and rebuilds field evidence.
    result = upload(client, app_id, 'bill').json()
    assert not result['fields']['full_name']['confirmed']
    assert not any(i['code'] == 'conflict_full_name' for i in result['issues'])
    assert len(result['documents']) == 4


@pytest.mark.parametrize('key,value,code', [
    ('admission_date', '2026-10-20', 'date_order'),
    ('discharge_date', '2027-01-01', 'outside_discharge_date'),
    ('policy_start', 'invalid', 'invalid_policy_start'),
    ('bank_account_last4', '12345', 'invalid_bank'),
    ('bill_total', '-1', 'invalid_amount'),
    ('bill_total', 'NaN', 'invalid_amount'),
    ('bill_total', 'Infinity', 'invalid_amount'),
    ('bill_total', '500001', 'over_limit'),
    ('policy_number', 'REAL-POLICY-123', 'unsupported_policy'),
])
def test_invalid_values_block_readiness(client, key, value, code):
    app_id, _ = demo(client, 'complete')
    r = client.patch(f'/api/applications/{app_id}/fields/{key}', json={'value': value})
    assert r.status_code == 200
    assert any(i['code'] == code for i in r.json()['issues'])
    assert client.post(f'/api/applications/{app_id}/review').status_code == 409


def test_bad_upload_preserves_existing_progress(client):
    app_id, record = demo(client, 'missing')
    bad = upload(client, app_id, 'policy', b'not a pdf')
    assert bad.status_code == 415
    bad = upload(client, app_id, 'policy', pdf_bytes('Unreadable', ['No supported fields']))
    assert bad.status_code == 422
    result = client.get(f'/api/applications/{app_id}').json()
    assert result['revision'] == record['revision']
    assert len(result['documents']) == 3


def test_missing_fields_in_individual_document(client):
    app_id, _ = demo(client, 'complete')
    incomplete = pdf_bytes('Bill', ['Patient name: Aarav Sharma', 'Bill total INR: 48500'])
    result = upload(client, app_id, 'bill', incomplete).json()
    # Dates exist in discharge summary, but the bill itself still needs verification.
    assert any(i['code'].startswith('unreadable_') and i['field'] == 'admission_date' for i in result['issues'])


def test_remove_document_invalidates_review_and_original_route(client):
    app_id, record = demo(client, 'complete')
    client.post(f'/api/applications/{app_id}/review')
    doc = record['documents'][0]
    assert client.get(f'/api/applications/{app_id}/documents/{doc["id"]}/file').content.startswith(b'%PDF')
    result = client.delete(f'/api/applications/{app_id}/documents/{doc["id"]}').json()
    assert result['status'] == 'collecting'
    assert result['reviewed_at'] is None
    assert client.get(f'/api/applications/{app_id}/documents/{doc["id"]}/file').status_code == 404


def test_grounded_chat_and_unknown_question(client):
    app_id, _ = demo(client, 'missing')
    record = client.post(f'/api/applications/{app_id}/messages', json={'text': 'What documents do I need?'}).json()
    answer = record['messages'][-1]
    assert answer['citations']
    assert 'bank' in answer['text'].lower()
    record = client.post(f'/api/applications/{app_id}/messages', json={'text': 'Who won Wimbledon?'}).json()
    assert 'cannot verify' in record['messages'][-1]['text']
    assert record['messages'][-1]['citations'] == []


def test_cloud_configuration_fail_closed(client, monkeypatch):
    app_id = new(client)
    monkeypatch.setattr(settings, 'oneflow_mode', 'cloud')
    monkeypatch.setattr(settings, 'google_cloud_project', '')
    monkeypatch.setattr(settings, 'document_ai_processor_id', '')
    assert upload(client, app_id, 'policy').status_code == 503
    assert client.post(f'/api/applications/{app_id}/demo', json={'scenario': 'complete'}).status_code == 409


def test_vertex_extraction_discards_invented_evidence(client, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(settings, 'oneflow_mode', 'cloud')
    captured = {}
    def generate_content(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(text=json.dumps({'fields': [
            {'key': 'full_name', 'value': 'Invented Name', 'page': 1, 'quote': 'Patient name: Invented Name'},
            {'key': 'policy_number', 'value': 'POC-2026-001', 'page': 1, 'quote': 'Policy number: POC-2026-001'},
        ]}))
    monkeypatch.setattr(providers, 'vertex_client', lambda: SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    result = providers.extract([{'page': 1, 'text': 'Policy number: POC-2026-001'}], 'policy')
    assert len(result) == 1 and result[0]['key'] == 'policy_number'
    assert captured['config'].response_mime_type == 'application/json'


def test_vertex_evidence_requires_exact_amount_not_substring(client, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(settings, 'oneflow_mode', 'cloud')
    def generate_content(**kwargs):
        return SimpleNamespace(text=json.dumps({'fields': [
            {'key': 'bill_total', 'value': '850', 'page': 1, 'quote': 'Bill total INR: 48,500.00'},
            {'key': 'bill_total', 'value': '48500', 'page': 1, 'quote': 'Bill total INR: 48,500.00'},
        ]}))
    monkeypatch.setattr(providers, 'vertex_client', lambda: SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    values = providers.extract([{'page': 1, 'text': 'Bill total INR: 48,500.00'}], 'bill')
    assert len(values) == 1 and values[0]['value'] == '48500'


def test_document_ai_adapter_uses_regional_processor(client, monkeypatch):
    from types import SimpleNamespace
    from google.cloud import documentai
    monkeypatch.setattr(settings, 'oneflow_mode', 'cloud')
    monkeypatch.setattr(settings, 'google_cloud_project', 'test-project')
    monkeypatch.setattr(settings, 'document_ai_location', 'eu')
    monkeypatch.setattr(settings, 'document_ai_processor_id', 'processor123')
    captured = {}
    class FakeClient:
        def __init__(self, client_options): captured['endpoint'] = client_options.api_endpoint
        def processor_path(self, project, location, processor): return f'projects/{project}/locations/{location}/processors/{processor}'
        def process_document(self, request, timeout):
            captured['request'] = request
            text = 'Patient name: Aarav Sharma'
            segment = documentai.Document.TextAnchor.TextSegment(start_index=0, end_index=len(text))
            anchor = documentai.Document.TextAnchor(text_segments=[segment])
            layout = documentai.Document.Page.Layout(text_anchor=anchor)
            doc = documentai.Document(text=text, pages=[documentai.Document.Page(page_number=1, layout=layout)])
            return SimpleNamespace(document=doc)
    monkeypatch.setattr(documentai, 'DocumentProcessorServiceClient', FakeClient)
    pages = providers.read_pages(b'%PDF-test', 'application/pdf')
    assert captured['endpoint'] == 'eu-documentai.googleapis.com'
    assert captured['request'].name == 'projects/test-project/locations/eu/processors/processor123'
    assert pages[0]['text'] == 'Patient name: Aarav Sharma'


def test_database_connections_release_file_handles(client):
    from app import store
    new(client)
    store.all_applications()
    database = settings.oneflow_data_dir / 'oneflow.db'
    renamed = database.with_suffix('.backup')
    database.rename(renamed)
    renamed.rename(database)
