from io import BytesIO
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings


def test_simulated_submission_tracking_and_duplicate_protection(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'oneflow_data_dir', tmp_path)
    monkeypatch.setattr(settings, 'oneflow_mode', 'demo')
    with TestClient(app) as client:
        created = client.post('/api/applications', json={'title': 'Submission test'}).json()
        app_id = created['id']
        assert client.post(f'/api/applications/{app_id}/demo', json={'scenario': 'complete'}).status_code == 200
        assert client.post(f'/api/applications/{app_id}/review').status_code == 200
        assert client.get(f'/api/applications/{app_id}/export').status_code == 200
        submitted = client.post(f'/api/applications/{app_id}/submit', json={'consent': True})
        assert submitted.status_code == 201
        claim = submitted.json()['claim']
        assert claim['acknowledgement_id'].startswith('SIM-')
        assert claim['claim_amount'] == '48500'
        assert client.post(f'/api/applications/{app_id}/submit', json={'consent': True}).status_code == 409
        assert client.get(f'/api/applications/{app_id}/claim').json()['claim']['claim_id'] == claim['claim_id']


def test_simulated_insurer_clarification_and_decision_are_persisted(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'oneflow_data_dir', tmp_path)
    monkeypatch.setattr(settings, 'oneflow_mode', 'demo')
    with TestClient(app) as client:
        app_id = client.post('/api/applications', json={'title': 'Decision test'}).json()['id']
        client.post(f'/api/applications/{app_id}/demo', json={'scenario': 'complete'})
        client.post(f'/api/applications/{app_id}/review')
        client.get(f'/api/applications/{app_id}/export')
        client.post(f'/api/applications/{app_id}/submit', json={'consent': True})
        assert client.post(f'/api/applications/{app_id}/claim/admin-action', headers={'X-OneFlow-Admin': 'simulator-admin'}, json={'action': 'request_information', 'explanation': 'Please provide the missing clinical note.'}).status_code == 200
        assert client.post(f'/api/applications/{app_id}/claim/clarification', json={'response': 'The requested clinical note is attached.'}).status_code == 200
        response = client.post(f'/api/applications/{app_id}/claim/admin-action', headers={'X-OneFlow-Admin': 'simulator-admin'}, json={'action': 'partial_approve', 'explanation': 'Eligible items approved after review.'})
        assert response.json()['claim']['status'] == 'partially_approved'
        settled = client.post(f'/api/applications/{app_id}/claim/admin-action', headers={'X-OneFlow-Admin': 'simulator-admin'}, json={'action': 'settle'})
        assert settled.json()['claim']['settlement']['reference'].startswith('SIM-SET-')
        assert len(settled.json()['insurer_events']) >= 4
