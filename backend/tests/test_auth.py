from datetime import timedelta

import jwt

from app.config.settings import settings
from app.services.auth_service import create_token

from .conftest import register


def test_health_and_ready(client):
    assert client.get("/health").json() == {"status": "ok"}
    r = client.get("/ready")
    assert r.status_code == 200 and r.json()["checks"]["database"] == "ok"


def test_register_returns_token_and_never_leaks_hash(client):
    u = register(client)
    assert u["user"]["email"] == u["email"]
    assert "password_hash" not in u["user"] and "password" not in u["user"]


def test_register_duplicate_email_case_insensitive(client, user):
    r = client.post("/api/auth/register", json={"name": "X", "email": user["email"].upper(), "password": "Another1!"})
    assert r.status_code == 409


def test_register_validation(client):
    bad = [
        {"name": "A", "email": "not-an-email", "password": "Passw0rd!"},
        {"name": "A", "email": "a@b.com", "password": "short"},
        {"name": "   ", "email": "a@b.com", "password": "Passw0rd!"},
        {"email": "a@b.com", "password": "Passw0rd!"},
    ]
    for body in bad:
        assert client.post("/api/auth/register", json=body).status_code == 422, body


def test_login_success_and_failures(client, user):
    ok = client.post("/api/auth/login", json={"email": user["email"], "password": user["password"]})
    assert ok.status_code == 200 and ok.json()["access_token"]
    wrong = client.post("/api/auth/login", json={"email": user["email"], "password": "WrongPass1"})
    assert wrong.status_code == 401
    unknown = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "Whatever1"})
    assert unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]  # no account enumeration


def test_login_throttle(client, user):
    for _ in range(10):
        client.post("/api/auth/login", json={"email": user["email"], "password": "nope-nope"})
    r = client.post("/api/auth/login", json={"email": user["email"], "password": user["password"]})
    assert r.status_code == 429


def test_me_requires_valid_token(client, user):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    r = client.get("/api/auth/me", headers=user["headers"])
    assert r.status_code == 200 and r.json()["user"]["name"] == "Alice"


def test_expired_and_forged_tokens_rejected(client, user):
    expired = create_token(user["user"], expires_delta=timedelta(seconds=-5))
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    forged = jwt.encode({"sub": user["user"]["id"], "tv": 0, "iat": 0, "exp": 9999999999}, "wrong-secret-" + "y" * 30,
                        algorithm="HS256")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    none_alg = jwt.encode({"sub": user["user"]["id"], "tv": 0, "iat": 0, "exp": 9999999999}, None, algorithm="none")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {none_alg}"}).status_code == 401


def test_profile_update(client, user):
    r = client.patch("/api/auth/me", headers=user["headers"], json={"name": "Alice B", "household_size": 3})
    assert r.status_code == 200 and r.json()["user"]["name"] == "Alice B"
    assert client.get("/api/auth/me", headers=user["headers"]).json()["user"]["household_size"] == 3
    assert client.patch("/api/auth/me", headers=user["headers"], json={"name": " "}).status_code == 422


def test_change_password_invalidates_old_tokens(client, user):
    bad = client.post("/api/auth/change-password", headers=user["headers"],
                      json={"current_password": "wrong-pass", "new_password": "NewPassw0rd"})
    assert bad.status_code == 400
    r = client.post("/api/auth/change-password", headers=user["headers"],
                    json={"current_password": user["password"], "new_password": "NewPassw0rd"})
    assert r.status_code == 200
    new_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=user["headers"]).status_code == 401
    assert client.get("/api/auth/me", headers=new_headers).status_code == 200
    assert client.post("/api/auth/login", json={"email": user["email"], "password": user["password"]}).status_code == 401
    assert client.post("/api/auth/login", json={"email": user["email"], "password": "NewPassw0rd"}).status_code == 200


def test_missing_jwt_secret_fails_closed(client, user, monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret_key", "")
    assert client.get("/api/auth/me", headers=user["headers"]).status_code == 503


def test_delete_account_removes_all_user_data(client, user, other_user):
    h = user["headers"]
    client.post("/api/pantry", headers=h, json={"items": [{"name": "tomato", "quantity": 2, "expiry_date": "2030-01-01"}]})
    client.post("/api/expenses", headers=h, json={"title": "Veg", "amount": 50})
    client.post("/api/shopping", headers=h, json={"name": "Milk"})
    client.post("/api/expenses", headers=other_user["headers"], json={"title": "Bob's", "amount": 10})

    assert client.post("/api/auth/delete-account", headers=h, json={"password": "wrong-one"}).status_code == 400
    assert client.post("/api/auth/delete-account", headers=h, json={"password": user["password"]}).status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 401
    assert client.post("/api/auth/login", json={"email": user["email"], "password": user["password"]}).status_code == 401
    from app.database.connection import Database
    db = Database.get_db()
    uid = user["user"]["id"]
    for coll in ("pantry_items", "expenses", "shopping_items", "meal_plans"):
        assert db[coll].count_documents({"user_id": uid}) == 0
    assert client.get("/api/expenses", headers=other_user["headers"]).json()["expense_count"] == 1
