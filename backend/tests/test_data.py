import uuid
from datetime import datetime, timedelta

import pytest

from app.services import gemini_service

from .conftest import register

PRIVATE_ENDPOINTS = [
    ("get", "/api/pantry"), ("post", "/api/pantry"), ("patch", "/api/pantry/tomato"),
    ("delete", "/api/pantry/tomato"), ("post", "/api/pantry/consume"), ("post", "/api/pantry/reset"),
    ("post", "/api/pantry/predict-expiry"), ("post", "/api/pantry/refresh-all-expiry"),
    ("get", "/api/expenses"), ("post", "/api/expenses"), ("delete", "/api/expenses/abc"),
    ("get", "/api/shopping"), ("post", "/api/shopping"), ("patch", "/api/shopping/abc"),
    ("delete", "/api/shopping/abc"), ("post", "/api/shopping/clear-checked"),
    ("post", "/api/recipes/recommend"), ("get", "/api/meals/plan"), ("post", "/api/meals/generate"),
    ("put", "/api/meals/update"), ("delete", "/api/meals/plan"), ("get", "/api/ai/insights"),
    ("get", "/api/analytics"), ("post", "/api/receipt/confirm"), ("patch", "/api/auth/me"),
    ("post", "/api/auth/change-password"), ("post", "/api/auth/delete-account"),
]


@pytest.mark.parametrize("method,path", PRIVATE_ENDPOINTS)
def test_private_endpoints_require_auth(client, method, path):
    r = getattr(client, method)(path, **({"json": {}} if method in ("post", "patch", "put") else {}))
    assert r.status_code == 401, f"{method.upper()} {path} -> {r.status_code}"


def _find(view, iid):
    return next(i for i in view if i["ingredient_id"] == iid)


def test_pantry_add_edit_delete(client, user):
    h = user["headers"]
    view = client.get("/api/pantry", headers=h).json()
    assert len(view) == 22 and not any(i["in_stock"] for i in view)

    expiry = (datetime.utcnow() + timedelta(days=5)).strftime("%Y-%m-%d")
    r = client.post("/api/pantry", headers=h, json={"items": [
        {"name": "tomatoes", "quantity": 4, "unit": "pcs", "expiry_date": expiry},
        {"name": "Paneer", "quantity": 200, "unit": "g", "expiry_date": expiry},
    ]})
    assert r.status_code == 200
    tomato = _find(r.json(), "tomato")
    assert tomato["in_stock"] and tomato["display_quantity"] == "4 pcs"
    assert tomato["expiry_display"] == "In 5 days" and tomato["expiry_status"] == "use_soon"
    assert _find(r.json(), "paneer")["display_quantity"] == "200 g"

    r = client.patch("/api/pantry/tomato", headers=h, json={"quantity": 1.5, "unit": "kg", "expiry_date": None})
    assert r.status_code == 200 and r.json()["display_quantity"] == "1.5 kg"
    assert r.json()["expiry_display"] == "No expiry set"

    assert client.patch("/api/pantry/carrot", headers=h, json={"quantity": 1, "unit": "pcs"}).status_code == 404
    assert client.delete("/api/pantry/tomato", headers=h).status_code == 200
    assert client.delete("/api/pantry/tomato", headers=h).status_code == 404
    assert not _find(client.get("/api/pantry", headers=h).json(), "tomato")["in_stock"]


def test_pantry_add_without_expiry_uses_labelled_estimate(client, user):
    r = client.post("/api/pantry", headers=user["headers"], json={"items": [{"name": "carrot", "quantity": 3}]})
    carrot = _find(r.json(), "carrot")
    assert carrot["earliest_expiry"] is not None
    assert carrot["ai_predicted"] is False  # no Gemini in tests -> baseline table, labelled as such


def test_pantry_idempotency(client, user):
    body = {"items": [{"name": "potato", "quantity": 1, "unit": "kg", "expiry_date": "2030-01-01"}],
            "idempotency_key": "scan-123"}
    client.post("/api/pantry", headers=user["headers"], json=body)
    r = client.post("/api/pantry", headers=user["headers"], json=body)
    assert _find(r.json(), "potato")["display_quantity"] == "1 kg"


def test_consume_converts_units(client, user):
    h = user["headers"]
    client.post("/api/pantry", headers=h, json={"items": [
        {"name": "potato", "quantity": 1, "unit": "kg", "expiry_date": "2030-01-01"}]})
    r = client.post("/api/pantry/consume", headers=h, json={"ingredient_id": "potato", "quantity": 250, "unit": "g"})
    assert r.status_code == 200 and r.json()["ingredient"]["display_quantity"] == "750 g"
    r = client.post("/api/pantry/consume", headers=h, json={"ingredient_id": "potato", "quantity": 750, "unit": "g"})
    assert r.json()["ingredient"]["in_stock"] is False
    assert client.post("/api/pantry/consume", headers=h,
                       json={"ingredient_id": "potato", "quantity": 1, "unit": "g"}).status_code == 400


def test_user_isolation(client, user, other_user):
    a, b = user["headers"], other_user["headers"]
    client.post("/api/pantry", headers=a, json={"items": [{"name": "lemon", "quantity": 6, "expiry_date": "2030-01-01"}]})
    exp = client.post("/api/expenses", headers=a, json={"title": "Veg", "amount": 120.5}).json()["expense"]
    item = client.post("/api/shopping", headers=a, json={"name": "Milk"}).json()

    assert not _find(client.get("/api/pantry", headers=b).json(), "lemon")["in_stock"]
    assert client.get("/api/expenses", headers=b).json()["expense_count"] == 0
    assert client.get("/api/shopping", headers=b).json()["items"] == []

    assert client.delete("/api/pantry/lemon", headers=b).status_code == 404
    assert client.delete(f"/api/expenses/{exp['id']}", headers=b).status_code == 404
    assert client.patch(f"/api/shopping/{item['id']}", headers=b, json={"checked": True}).status_code == 404
    assert client.delete(f"/api/shopping/{item['id']}", headers=b).status_code == 404
    client.post("/api/pantry/reset", headers=b)

    assert _find(client.get("/api/pantry", headers=a).json(), "lemon")["in_stock"]
    assert client.get("/api/expenses", headers=a).json()["expense_count"] == 1
    assert client.get("/api/shopping", headers=a).json()["items"][0]["checked"] is False


def test_client_supplied_user_id_is_ignored(client, user, other_user):
    client.post("/api/expenses", headers=other_user["headers"],
                json={"title": "Sneaky", "amount": 10, "user_id": user["user"]["id"]})
    assert client.get("/api/expenses", headers=user["headers"]).json()["expense_count"] == 0
    r = client.get(f"/api/expenses?user_id={other_user['user']['id']}", headers=user["headers"])
    assert r.json()["expense_count"] == 0


def test_expenses_crud_and_validation(client, user):
    h = user["headers"]
    today = datetime.utcnow().strftime("%Y-%m-%d")
    assert client.post("/api/expenses", headers=h, json={"title": "X", "amount": 0}).status_code == 422
    assert client.post("/api/expenses", headers=h, json={"title": "X", "amount": 5, "date": "15/10/2026"}).status_code == 422
    r = client.post("/api/expenses", headers=h, json={"title": "Weekly veg", "amount": 450.75, "category": "Vegetables",
                                                      "date": today})
    assert r.status_code == 201
    summary = client.get("/api/expenses", headers=h).json()
    assert summary["total_this_month"] == 450.75 and summary["weekly_spending"][3] == 450.75
    assert summary["category_breakdown"][0] == {"category": "Vegetables", "amount": 450.75, "percentage": 100.0}
    assert client.get("/api/expenses?month=2001-01", headers=h).json()["expenses"] == []
    assert client.get("/api/expenses?month=bad", headers=h).status_code == 422
    assert client.delete(f"/api/expenses/{r.json()['expense']['id']}", headers=h).status_code == 200
    assert client.get("/api/expenses", headers=h).json()["expense_count"] == 0


def test_shopping_list(client, user):
    h = user["headers"]
    a = client.post("/api/shopping", headers=h, json={"name": "tomatoes", "quantity": "1 kg"}).json()
    assert a["name"] == "Tomato" and a["ingredient_id"] == "tomato"
    dup = client.post("/api/shopping", headers=h, json={"name": "Tomato"}).json()
    assert dup["id"] == a["id"]
    b = client.post("/api/shopping", headers=h, json={"name": "Bread"}).json()
    assert client.patch(f"/api/shopping/{b['id']}", headers=h, json={"checked": True}).json()["checked"] is True
    assert client.post("/api/shopping/clear-checked", headers=h).json()["deleted"] == 1
    items = client.get("/api/shopping", headers=h).json()["items"]
    assert [i["name"] for i in items] == ["Tomato"]


def test_shopping_suggests_expired_pantry_items(client, user):
    h = user["headers"]
    past = (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%d")
    client.post("/api/pantry", headers=h, json={"items": [{"name": "cabbage", "quantity": 1, "expiry_date": past}]})
    sugg = client.get("/api/shopping", headers=h).json()["suggestions"]
    assert sugg and sugg[0]["ingredient_id"] == "cabbage" and sugg[0]["reason"] == "Expired"


def test_receipt_confirm_is_idempotent(client, user):
    h = user["headers"]
    body = {"idempotency_key": uuid.uuid4().hex,
            "items": [{"name": "Tomato", "quantity": 2, "unit": "kg", "expiry_date": "2030-01-01"}],
            "expense": {"title": "Fresh Mart", "amount": 240, "date": datetime.utcnow().strftime("%Y-%m-%d")}}
    first = client.post("/api/receipt/confirm", headers=h, json=body)
    second = client.post("/api/receipt/confirm", headers=h, json=body)
    assert first.status_code == 200 and first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert client.get("/api/expenses", headers=h).json()["expense_count"] == 1
    assert _find(client.get("/api/pantry", headers=h).json(), "tomato")["display_quantity"] == "2 kg"


def test_receipt_process_validation(client, user, monkeypatch):
    h = user["headers"]
    r = client.post("/api/receipt/process", headers=h, files={"file": ("a.jpg", b"not an image", "image/jpeg")})
    assert r.status_code == 415
    jpeg = b"\xff\xd8\xff\xe0" + b"0" * 100
    r = client.post("/api/receipt/process", headers=h, files={"file": ("a.jpg", jpeg, "image/jpeg")})
    assert r.status_code == 503  # Gemini not configured -> clear error, no fake data
    from app.config.settings import settings
    monkeypatch.setattr(settings, "max_upload_mb", 0)
    assert client.post("/api/receipt/process", headers=h, files={"file": ("a.jpg", jpeg, "image/jpeg")}).status_code == 413


def test_receipt_parsing_never_invents_values(client, user, monkeypatch):
    raw = {"is_receipt": True, "store_name": "Fresh Mart", "purchase_date": "2026-13-40", "total": "1,234.50",
           "items": [{"name": "TOMATO", "quantity": None, "unit": "litre", "price": "40"},
                     {"name": "", "price": 3}, {"name": "Milk", "quantity": -1, "unit": "bag", "price": None}]}
    monkeypatch.setattr(gemini_service.gemini_client, "generate_json", lambda *a, **k: raw)
    jpeg = b"\xff\xd8\xff\xe0" + b"0" * 100
    r = client.post("/api/receipt/process", headers=user["headers"], files={"file": ("r.jpg", jpeg, "image/jpeg")})
    assert r.status_code == 200
    out = r.json()
    assert out["purchase_date"] is None and out["total"] == 1234.5
    assert [i["name"] for i in out["items"]] == ["TOMATO", "Milk"]
    assert out["items"][0]["ingredient_id"] == "tomato" and out["items"][0]["unit"] == "l"
    assert out["items"][1]["quantity"] is None and out["items"][1]["unit"] is None and out["items"][1]["price"] is None


def test_recipes_errors_are_explicit(client, user):
    h = user["headers"]
    empty = client.post("/api/recipes/recommend", headers=h, json={}).json()
    assert empty["recipes"] == [] and "pantry" in empty["message"].lower()
    client.post("/api/pantry", headers=h, json={"items": [{"name": "tomato", "quantity": 3, "expiry_date": "2030-01-01"}]})
    assert client.post("/api/recipes/recommend", headers=h, json={}).status_code == 503


def test_analytics_is_real(client, user):
    h = user["headers"]
    soon = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
    client.post("/api/pantry", headers=h, json={"items": [{"name": "radish", "quantity": 1, "expiry_date": soon},
                                                          {"name": "pumpkin", "quantity": 1, "expiry_date": "2030-01-01"}]})
    a = client.get("/api/analytics", headers=h).json()
    assert a["total_pantry_items"] == 2 and a["expiring_soon_count"] == 1 and a["fresh_items_count"] == 1
    assert [i["ingredient_id"] for i in a["at_risk_items"]] == ["radish"]
    assert "waste_saved" not in a
    insights = client.get("/api/ai/insights", headers=h).json()
    assert insights["source"] == "rules" and len(insights["insights"]) == 4


def test_meal_plan_requires_pantry_and_ai(client, user):
    h = user["headers"]
    assert client.post("/api/meals/generate", headers=h, json={}).status_code == 400
    client.post("/api/pantry", headers=h, json={"items": [{"name": "tomato", "quantity": 3, "expiry_date": "2030-01-01"}]})
    assert client.post("/api/meals/generate", headers=h, json={}).status_code == 502
    assert client.get("/api/meals/plan", headers=h).json()["days"] == []
