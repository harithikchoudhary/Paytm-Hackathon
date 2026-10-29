"""Explicit opt-in integration check: two synthetic PDFs through real cloud APIs."""
import argparse
import sys
import tempfile
from contextlib import nullcontext
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from app.config import settings
from app.main import app
from app.samples import sample


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keep', action='store_true', help='Retain the verified cashless simulation in the normal workspace.')
    args = parser.parse_args()
    if settings.oneflow_mode != 'cloud' or settings.cloud_missing():
        raise SystemExit('Configure cloud mode and ADC first.')
    previous = settings.oneflow_data_dir
    context = nullcontext(str(previous)) if args.keep else tempfile.TemporaryDirectory(prefix='oneflow-cashless-')
    with context as directory:
        settings.oneflow_data_dir = Path(directory)
        try:
            with TestClient(app) as client:
                response = client.post('/api/applications', json={'title': 'Cashless cloud check - simulation',
                    'journey': 'cashless', 'issued_policy_id': 'customer-health-2026', 'member_id': 'aarav'})
                response.raise_for_status()
                app_id = response.json()['id']
                response = client.put(f'/api/applications/{app_id}/cashless/details', json={
                    'member_id': 'aarav', 'hospital_id': 'sunrise-pune', 'admission_type': 'planned',
                    'admission_date': '2026-10-31', 'estimated_amount': '80000', 'identity_ready': True,
                    'treatment_summary': 'Planned orthopaedic procedure advised by the treating doctor'})
                response.raise_for_status()
                for kind in ('admission_advice', 'cost_estimate'):
                    response = client.post(f'/api/applications/{app_id}/documents', data={'kind': kind},
                        files={'file': (kind + '.pdf', sample(kind), 'application/pdf')})
                    if response.status_code != 200:
                        raise RuntimeError(response.text)
                    print(kind, 'Document AI + Vertex AI passed;', len(response.json()['documents'][-1]['extracted']), 'evidence-linked fields', flush=True)
                assert response.json()['issues'] == [], response.json()['issues']
                for action in ['submit', 'request_information', 'resubmit', 'authorize', 'discharge_review', 'settle']:
                    response = client.post(f'/api/applications/{app_id}/cashless/simulate', json={
                        'action': action, 'clarification': 'Synthetic estimate includes the advised procedure and hospital stay.'})
                    response.raise_for_status()
                record = response.json()
                assert record['cashless']['status'] == 'settled'
                assert record['cashless']['authorized_amount'] == '64000.00'
                assert record['cashless']['simulation'] is True
                response = client.post(f'/api/applications/{app_id}/messages', json={'text': 'Does a sample hospital listing guarantee actual cashless authorization?'})
                response.raise_for_status()
                answer = response.json()['messages'][-1]
                assert any(c['id'] in ('H2', 'H3', 'P2') for c in answer['citations'])
                response = client.get(f'/api/applications/{app_id}/cashless/brief')
                response.raise_for_status()
                assert response.content.startswith(b'%PDF')
                print('CASHLESS CLOUD CHECK PASSED: existing policy -> cloud extraction -> preparation -> simulated query/resubmission/authorization/discharge/settlement -> cited answer -> PDF brief', flush=True)
                if args.keep:
                    print('Retained simulation:', app_id, flush=True)
        finally:
            settings.oneflow_data_dir = previous


if __name__ == '__main__':
    main()
