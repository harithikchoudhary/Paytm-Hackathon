from io import BytesIO
from zipfile import ZipFile
import json
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.samples import sample, pdf_bytes


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'oneflow_data_dir', tmp_path)
    monkeypatch.setattr(settings, 'oneflow_mode', 'demo')
    with TestClient(app) as client:
        yield client


def new(client, journey='cashless', member='aarav'):
    response = client.post('/api/applications', json={'title': 'Existing policy claim', 'journey': journey,
        'issued_policy_id': 'customer-health-2026', 'member_id': member})
    assert response.status_code == 201, response.text
    return response.json()


def upload(client, app_id, kind, content=None):
    return client.post(f'/api/applications/{app_id}/documents', data={'kind': kind},
        files={'file': (kind + '.pdf', content or sample(kind), 'application/pdf')})


def details(**kwargs):
    return {'member_id': 'aarav', 'hospital_id': 'sunrise-pune', 'admission_type': 'planned',
        'admission_date': '2026-10-31', 'treatment_summary': 'Planned orthopaedic procedure advised by the treating doctor',
        'estimated_amount': '80000', 'identity_ready': True, **kwargs}


def prepared(client):
    record = new(client)
    app_id = record['id']
    response = client.put(f'/api/applications/{app_id}/cashless/details', json=details())
    assert response.status_code == 200
    for kind in ('admission_advice', 'cost_estimate'):
        response = upload(client, app_id, kind)
        assert response.status_code == 200, response.text
    assert response.json()['issues'] == []
    return app_id


def advance(client, app_id, action, **kwargs):
    return client.post(f'/api/applications/{app_id}/cashless/simulate', json={'action': action, **kwargs})


def test_existing_policy_preloaded_and_protected(client):
    record = new(client, 'reimbursement')
    assert record['fields']['policy_number']['value'] == 'DEMO-HEALTH-2026-001'
    assert record['issued_policy']['is_demo'] is True
    assert any(c['id'] == 'H2' and c['page'] == 49 for c in record['policy_context']['clauses'])
    assert any(c['id'] == 'P1' for c in record['policy_context']['clauses'])
    doc = record['documents'][0]
    assert doc['preloaded'] and 'path' not in doc
    app_id = record['id']
    assert client.delete(f'/api/applications/{app_id}/documents/{doc["id"]}').status_code == 409
    assert upload(client, app_id, 'policy').status_code == 409
    assert client.patch(f'/api/applications/{app_id}/fields/full_name', json={'value': 'Other Person'}).status_code == 409


def test_bound_reimbursement_with_only_claim_uploads(client):
    app_id = new(client, 'reimbursement')['id']
    for kind in ('bill', 'discharge', 'bank_proof'):
        response = upload(client, app_id, kind)
        assert response.status_code == 200, response.text
    assert response.json()['status'] == 'review'
    assert response.json()['issues'] == []
    assert client.post(f'/api/applications/{app_id}/review').json()['status'] == 'ready'
    response = client.get(f'/api/applications/{app_id}/export')
    with ZipFile(BytesIO(response.content)) as z:
        assert 'policy-source-reference.json' in z.namelist()
        assert 'trusted-synthetic-policy.pdf' not in z.namelist()
        data = json.loads(z.read('claim-data.json'))
        assert data['policy_id'] == 'HDFHLIP26058V082526'


def test_cashless_requires_existing_policy_and_valid_patient(client):
    assert client.post('/api/applications', json={'journey': 'cashless'}).status_code == 422
    assert client.post('/api/applications', json={'issued_policy_id': 'invalid'}).status_code == 404
    assert client.post('/api/applications', json={'issued_policy_id': 'customer-health-2026', 'member_id': 'stranger'}).status_code == 422
    record = new(client, member='meera')
    assert record['fields']['full_name']['value'] == 'Meera Sharma'
    assert client.put(f'/api/applications/{record["id"]}/cashless/details', json=details()).status_code == 422


def test_invalid_state_advances_and_missing_documents_block(client):
    record = new(client)
    app_id = record['id']
    assert advance(client, app_id, 'authorize').status_code == 409
    assert advance(client, app_id, 'submit').status_code == 409
    assert client.get(f'/api/applications/{app_id}/cashless/brief').status_code == 409
    assert client.post(f'/api/applications/{app_id}/review').status_code == 409
    assert upload(client, app_id, 'bill').status_code == 422


def test_full_cashless_simulation_and_persistence(client):
    app_id = prepared(client)
    assert client.get(f'/api/applications/{app_id}/cashless/brief').content.startswith(b'%PDF')
    assert advance(client, app_id, 'submit').json()['cashless']['status'] == 'submitted'
    assert advance(client, app_id, 'request_information').json()['cashless']['status'] == 'information_required'
    assert advance(client, app_id, 'resubmit', clarification='short').status_code == 409
    assert advance(client, app_id, 'resubmit', clarification='Synthetic clarification: the estimate includes the advised procedure and hospital stay.').json()['cashless']['status'] == 'resubmitted'
    response = advance(client, app_id, 'authorize')
    assert response.json()['cashless']['authorized_amount'] == '64000.00'
    assert response.json()['cashless']['simulation'] is True
    assert advance(client, app_id, 'settle').status_code == 409
    assert advance(client, app_id, 'discharge_review').json()['cashless']['status'] == 'discharge_review'
    record = advance(client, app_id, 'settle').json()
    assert record['status'] == 'cashless_settled'
    assert record['progress'] == 100
    assert all(e['source'] == 'simulation' for e in record['cashless']['timeline'])
    assert 'No funds were transferred' in record['cashless']['timeline'][-1]['message']
    assert client.get(f'/api/applications/{app_id}').json()['cashless']['status'] == 'settled'
    assert client.get(f'/api/applications/{app_id}/export').status_code == 409


@pytest.mark.parametrize('change,code', [
    ({'hospital_id': 'city-delhi'}, 'network'),
    ({'admission_date': '2028-01-01'}, 'period'),
    ({'admission_date': 'bad-date!!'}, 'admission_date'),
    ({'estimated_amount': 'NaN'}, 'estimate'),
    ({'estimated_amount': '-1'}, 'estimate'),
    ({'identity_ready': False}, 'identity'),
])
def test_preparation_validation(client, change, code):
    app_id = new(client)['id']
    response = client.put(f'/api/applications/{app_id}/cashless/details', json=details(**change))
    assert response.status_code == 200, response.text
    assert any(i['code'] == code for i in response.json()['issues'])
    assert advance(client, app_id, 'submit').status_code == 409


def test_updates_invalidate_simulated_authorization(client):
    app_id = prepared(client)
    advance(client, app_id, 'submit')
    advance(client, app_id, 'authorize')
    response = client.put(f'/api/applications/{app_id}/cashless/details', json=details(admission_type='emergency'))
    assert response.json()['cashless']['status'] == 'draft'
    assert response.json()['cashless']['authorized_amount'] is None
    assert advance(client, app_id, 'settle').status_code == 409
    advance(client, app_id, 'submit')
    advance(client, app_id, 'authorize')
    response = upload(client, app_id, 'cost_estimate')
    assert response.json()['cashless']['status'] == 'draft'


def test_document_patient_and_cost_conflicts_block(client):
    app_id = prepared(client)
    bad = pdf_bytes('Estimate', ['Patient name: Another Person', 'Hospital name: Sunrise Care Hospital', 'Estimated amount INR: 90000'])
    response = upload(client, app_id, 'cost_estimate', bad)
    codes = [i['code'] for i in response.json()['issues']]
    assert any(c.startswith('patient_') for c in codes)
    assert any(c.startswith('cost_') for c in codes)
    assert advance(client, app_id, 'submit').status_code == 409


def test_incomplete_clinical_document_cannot_pass(client):
    app_id = prepared(client)
    response = upload(client, app_id, 'cost_estimate', pdf_bytes('Bad estimate', ['Patient name: Aarav Sharma']))
    assert any(i['code'].startswith('incomplete_') for i in response.json()['issues'])
    assert advance(client, app_id, 'submit').status_code == 409


def test_declined_simulation_and_injected_amount(client):
    app_id = prepared(client)
    advance(client, app_id, 'submit')
    assert advance(client, app_id, 'authorize', authorized_amount='9999999').status_code == 422
    assert advance(client, app_id, 'decline').json()['cashless']['status'] == 'declined'
    assert advance(client, app_id, 'authorize').status_code == 409
    assert client.get(f'/api/applications/{app_id}').json()['cashless']['authorized_amount'] is None


def test_cashless_policy_answers_reference_real_wording(client):
    app_id = new(client)['id']
    response = client.post(f'/api/applications/{app_id}/messages', json={'text': 'How does cashless hospital pre-authorization work?'})
    answer = response.json()['messages'][-1]
    assert any(c['id'] in ('H2', 'H3') for c in answer['citations'])
    assert all(c['id'] not in ('C1', 'C2', 'C3', 'C4', 'C5') for c in answer['citations'])
    hospitals = client.get('/api/hospitals?q=pune').json()
    assert hospitals['is_demo'] is True
    assert len(hospitals['hospitals']) == 1
