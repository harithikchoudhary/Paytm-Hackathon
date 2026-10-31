import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4
from .config import settings
from . import object_store

DB_NAME = 'oneflow.db'
DB_BACKUP_OBJECT = 'oneflow/metadata/oneflow.db'


def _db_path():
    return settings.oneflow_data_dir / DB_NAME


def _restore_db_if_needed():
    path = _db_path()
    if path.exists():
        return
    backup = object_store.get_raw(DB_BACKUP_OBJECT)
    if backup:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(backup)


def _backup_db():
    path = _db_path()
    if path.exists() and settings.gcs_bucket:
        object_store.put_raw(DB_BACKUP_OBJECT, path.read_bytes(), 'application/x-sqlite3')


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    settings.oneflow_data_dir.mkdir(parents=True, exist_ok=True)
    _restore_db_if_needed()
    db = sqlite3.connect(_db_path(), timeout=20)
    try:
        with db:
            db.execute('CREATE TABLE IF NOT EXISTS applications (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS claims (application_id TEXT PRIMARY KEY, body TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS insurer_events (id TEXT PRIMARY KEY, application_id TEXT NOT NULL, body TEXT NOT NULL)')
            yield db
    finally:
        # sqlite3's own context manager commits/rolls back but does not close.
        db.close()


def save(app):
    app['updated_at'] = now()
    with connect() as db:
        db.execute('INSERT OR REPLACE INTO applications VALUES (?, ?)', (app['id'], json.dumps(app)))
    _backup_db()
    return app


def get(app_id):
    with connect() as db:
        row = db.execute('SELECT body FROM applications WHERE id = ?', (app_id,)).fetchone()
    return json.loads(row[0]) if row else None


def all_applications():
    with connect() as db:
        rows = db.execute('SELECT body FROM applications').fetchall()
    return sorted([json.loads(row[0]) for row in rows], key=lambda x: x['updated_at'], reverse=True)


def create(title, journey='reimbursement', policy=None, member_id='aarav', owner_id='demo-user'):
    return save({
        'id': str(uuid4()), 'title': title, 'created_at': now(), 'updated_at': now(),
        'documents': [], 'corrections': {}, 'messages': [], 'audit': [],
        'reviewed_at': None, 'revision': 0, 'fields': {}, 'issues': [],
        'status': 'collecting', 'progress': 0, 'claim_details': {},
        'assistant_state': {'active_application_id': None, 'claim_id': None, 'claim_type': journey,
                           'stage': 'intake', 'pending_action': None, 'last_confirmation': None},
        'journey': journey, 'issued_policy': policy, 'member_id': member_id, 'owner_id': owner_id,
        'cashless': {'simulation': True, 'status': 'draft', 'details': {}, 'timeline': [], 'authorized_amount': None} if journey == 'cashless' else None,
    })


def mutate(app, event, details):
    app['revision'] += 1
    app['reviewed_at'] = None
    app['audit'].append({'at': now(), 'event': event, 'details': details})


def save_claim(claim):
    with connect() as db:
        db.execute('INSERT OR REPLACE INTO claims VALUES (?, ?)', (claim['application_id'], json.dumps(claim)))
    _backup_db()
    return claim


def get_claim(application_id):
    with connect() as db:
        row = db.execute('SELECT body FROM claims WHERE application_id = ?', (application_id,)).fetchone()
    return json.loads(row[0]) if row else None


def add_insurer_event(application_id, event):
    event = {**event, 'id': event.get('id', str(uuid4())), 'application_id': application_id}
    with connect() as db:
        db.execute('INSERT INTO insurer_events VALUES (?, ?, ?)', (event['id'], application_id, json.dumps(event)))
    _backup_db()
    return event


def insurer_events(application_id):
    with connect() as db:
        rows = db.execute('SELECT body FROM insurer_events WHERE application_id = ? ORDER BY rowid', (application_id,)).fetchall()
    return [json.loads(row[0]) for row in rows]
