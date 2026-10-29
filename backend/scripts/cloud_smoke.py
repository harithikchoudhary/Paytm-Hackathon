r"""Explicit opt-in cloud integration check; uses synthetic PDFs only and incurs API usage.

Run from repository root: .venv\Scripts\python.exe backend\scripts\cloud_smoke.py
"""
import sys
import tempfile
import argparse
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from app.config import settings
from app.main import app
from app.samples import sample


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keep', action='store_true', help='Keep the tested cloud application in the normal workspace for interactive review.')
    args = parser.parse_args()
    if settings.oneflow_mode != 'cloud' or settings.cloud_missing():
        raise SystemExit('Configure cloud mode, project ID, processor ID, and ADC before running this test.')
    previous_data_dir = settings.oneflow_data_dir
    from contextlib import nullcontext
    context = nullcontext(str(previous_data_dir)) if args.keep else tempfile.TemporaryDirectory(prefix='oneflow-cloud-test-')
    with context as directory:
        settings.oneflow_data_dir = Path(directory)
        try:
            with TestClient(app) as client:
                response = client.post('/api/applications', json={'title': 'Cloud integration test - synthetic'})
                response.raise_for_status()
                app_id = response.json()['id']
                for kind in ['policy', 'bill', 'discharge', 'bank_proof']:
                    response = client.post(f'/api/applications/{app_id}/documents', data={'kind': kind}, files={'file': (f'{kind}.pdf', sample(kind), 'application/pdf')})
                    if response.status_code != 200:
                        raise RuntimeError(f'{kind}: {response.status_code} {response.text}')
                    record = response.json()
                    print(f'{kind}: Document AI + Vertex AI OK; {len(record["documents"][-1]["extracted"])} evidence-linked fields', flush=True)
                assert record['status'] == 'review', record['issues']
                assert not [i for i in record['issues'] if i['severity'] == 'error'], record['issues']
                response = client.post(f'/api/applications/{app_id}/messages', json={'text': 'What does a ready packet mean? Does it mean the claim is approved?'})
                response.raise_for_status()
                answer = response.json()['messages'][-1]
                assert answer['citations'], answer
                print('Vertex policy answer OK; citations:', ', '.join(c['id'] for c in answer['citations']), flush=True)
                response = client.post(f'/api/applications/{app_id}/review')
                response.raise_for_status()
                assert response.json()['status'] == 'ready'
                response = client.get(f'/api/applications/{app_id}/export')
                response.raise_for_status()
                with ZipFile(BytesIO(response.content)) as z:
                    assert 'claim-summary.pdf' in z.namelist()
                    assert len([n for n in z.namelist() if n.startswith('documents/')]) == 4
                print('CLOUD END-TO-END PASSED: OCR -> extraction -> validation -> grounded answer -> review -> ZIP export', flush=True)
                if args.keep:
                    print('Saved cloud-verified application:', app_id, flush=True)
        finally:
            settings.oneflow_data_dir = previous_data_dir


if __name__ == '__main__':
    main()
