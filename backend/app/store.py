import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4
from .config import settings


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    settings.oneflow_data_dir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(settings.oneflow_data_dir / 'oneflow.db', timeout=20)
    try:
        with db:
            db.execute('CREATE TABLE IF NOT EXISTS applications (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
            yield db
    finally:
        # sqlite3's own context manager commits/rolls back but does not close.
        db.close()


def save(app):
    app['updated_at'] = now()
    with connect() as db:
        db.execute('INSERT OR REPLACE INTO applications VALUES (?, ?)', (app['id'], json.dumps(app)))
    return app


def get(app_id):
    with connect() as db:
        row = db.execute('SELECT body FROM applications WHERE id = ?', (app_id,)).fetchone()
    return json.loads(row[0]) if row else None


def all_applications():
    with connect() as db:
        rows = db.execute('SELECT body FROM applications').fetchall()
    return sorted([json.loads(row[0]) for row in rows], key=lambda x: x['updated_at'], reverse=True)


def create(title, journey='reimbursement', policy=None, member_id='aarav'):
    return save({
        'id': str(uuid4()), 'title': title, 'created_at': now(), 'updated_at': now(),
        'documents': [], 'corrections': {}, 'messages': [], 'audit': [],
        'reviewed_at': None, 'revision': 0, 'fields': {}, 'issues': [],
        'status': 'collecting', 'progress': 0,
        'journey': journey, 'issued_policy': policy, 'member_id': member_id,
        'cashless': {'simulation': True, 'status': 'draft', 'details': {}, 'timeline': [], 'authorized_amount': None} if journey == 'cashless' else None,
    })


def mutate(app, event, details):
    app['revision'] += 1
    app['reviewed_at'] = None
    app['audit'].append({'at': now(), 'event': event, 'details': details})
