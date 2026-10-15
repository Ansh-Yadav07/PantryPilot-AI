"""
Test configuration.

By default the API is tested against an in-memory mongomock database.
Set TEST_MONGODB_URI to run the same tests against a real MongoDB/Atlas
cluster; a uniquely named throwaway database is created and dropped, so
production data is never touched.
"""

import os
import uuid

import pytest

os.environ["ENVIRONMENT"] = "test"
os.environ["JWT_SECRET_KEY"] = "test-secret-" + "x" * 40
os.environ["GEMINI_API_KEY"] = ""  # unit tests never call the real Gemini API
os.environ["MONGODB_URI"] = os.environ.get("TEST_MONGODB_URI", "")
os.environ["DATABASE_NAME"] = f"pantrypilot_test_{uuid.uuid4().hex[:8]}"

from fastapi.testclient import TestClient  # noqa: E402

from app.config.settings import settings  # noqa: E402
from app.database.connection import Database  # noqa: E402

REAL_DB = bool(os.environ["MONGODB_URI"])


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret_key", os.environ["JWT_SECRET_KEY"])
    monkeypatch.setattr(settings, "gemini_api_key", "")
    if REAL_DB:
        settings.database_name = f"pantrypilot_test_{uuid.uuid4().hex[:8]}"
        Database.client = None
    else:
        import mongomock
        Database.client = mongomock.MongoClient()
    from app.main import app
    from app.routes import auth as auth_routes
    auth_routes._failed_attempts.clear()
    with TestClient(app) as c:
        yield c
    if REAL_DB:
        # The app's shutdown closed its client; use a fresh one for cleanup.
        assert settings.database_name.startswith("pantrypilot_test_")
        import certifi
        from pymongo import MongoClient
        cleanup = MongoClient(os.environ["MONGODB_URI"], tlsCAFile=certifi.where())
        cleanup.drop_database(settings.database_name)
        cleanup.close()
    Database.client = None


_counter = iter(range(10_000))


def register(client, name="Test User", password="Passw0rd!"):
    email = f"user{next(_counter)}_{uuid.uuid4().hex[:6]}@example.com"
    r = client.post("/api/auth/register", json={"name": name, "email": email, "password": password})
    assert r.status_code == 201, r.text
    body = r.json()
    return {"email": email, "password": password, "token": body["access_token"], "user": body["user"],
            "headers": {"Authorization": f"Bearer {body['access_token']}"}}


@pytest.fixture()
def user(client):
    return register(client, "Alice")


@pytest.fixture()
def other_user(client):
    return register(client, "Bob")
