import os
import sys

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app  
from config import TestConfig  
from extensions import db  


@pytest.fixture()
def app():
    app = create_app(TestConfig)

    from flask import g
    def _clear_csrf_cache():
        g.pop("csrf_token", None)  

    app.before_request_funcs.setdefault(None, []).insert(0, _clear_csrf_cache)

    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@event.listens_for(Engine, "connect")
def _sqlite_fk_on(dbapi_conn, _record):
    if dbapi_conn.__class__.__module__.startswith("sqlite3"):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()
