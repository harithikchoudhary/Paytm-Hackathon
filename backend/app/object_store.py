"""Durable document storage with a local fallback for development and tests."""

from pathlib import Path
from urllib.parse import urlparse

from .config import settings


def _client():
    from google.cloud import storage
    return storage.Client(project=settings.google_cloud_project or None)


def object_name(application_id: str, document_id: str, suffix: str) -> str:
    prefix = settings.gcs_prefix.strip('/') if settings.gcs_prefix else 'oneflow'
    return f"{prefix}/applications/{application_id}/documents/{document_id}{suffix}"


def put(application_id: str, document_id: str, suffix: str, content: bytes, content_type: str) -> str | None:
    if not settings.gcs_bucket:
        return None
    name = object_name(application_id, document_id, suffix)
    blob = _client().bucket(settings.gcs_bucket).blob(name)
    blob.upload_from_string(content, content_type=content_type)
    return f"gs://{settings.gcs_bucket}/{name}"


def put_raw(name: str, content: bytes, content_type: str = 'application/octet-stream') -> None:
    if not settings.gcs_bucket:
        return
    _client().bucket(settings.gcs_bucket).blob(name).upload_from_string(content, content_type=content_type)


def get_raw(name: str) -> bytes | None:
    if not settings.gcs_bucket:
        return None
    blob = _client().bucket(settings.gcs_bucket).blob(name)
    if not blob.exists():
        return None
    return blob.download_as_bytes()


def _blob(uri: str):
    parsed = urlparse(uri)
    if parsed.scheme != 'gs' or not parsed.netloc or not parsed.path:
        raise ValueError('Invalid cloud storage URI')
    return _client().bucket(parsed.netloc).blob(parsed.path.lstrip('/'))


def read(document: dict) -> bytes:
    local_path = document.get('path')
    if local_path and Path(local_path).exists():
        return Path(local_path).read_bytes()
    if document.get('storage_uri'):
        return _blob(document['storage_uri']).download_as_bytes()
    raise FileNotFoundError('Document content is no longer available')


def delete(document: dict) -> None:
    uri = document.get('storage_uri')
    if uri:
        blob = _blob(uri)
        if blob.exists():
            blob.delete()

