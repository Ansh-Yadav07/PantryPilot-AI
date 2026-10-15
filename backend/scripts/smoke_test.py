#!/usr/bin/env python3
"""
End-to-end check of a running PantryPilot API (local or deployed).

    python scripts/smoke_test.py https://your-api.onrender.com [--receipt path/to/receipt.jpg] [--skip-ai]

Creates two throwaway accounts, exercises every user journey through the real
API (MongoDB + Gemini), verifies that the accounts cannot see each other's
data, then deletes both accounts and all their data. Uses only the standard
library. Exit code 0 = all checks passed.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import date, timedelta

RESULTS = []


def call(base, method, path, token=None, body=None, files=None, timeout=120):
    url = f"{base}{path}"
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if files:
        boundary = uuid.uuid4().hex
        name, content, ctype = files
        data = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
                f"Content-Type: {ctype}\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None), time.time() - t0
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw), time.time() - t0
        except Exception:
            return e.code, raw.decode(errors="replace")[:200], time.time() - t0


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  — ' + str(detail)) if detail and not ok else ''}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base_url")
    ap.add_argument("--receipt", help="photo of a grocery receipt to test extraction")
    ap.add_argument("--skip-ai", action="store_true", help="skip Gemini-backed checks")
    a = ap.parse_args()
    root = a.base_url.rstrip("/").removesuffix("/api")
    api = root + "/api"

    s, b, t = call(root, "GET", "/health", timeout=90)
    check("GET /health", s == 200 and b == {"status": "ok"}, b)
    s, b, _ = call(root, "GET", "/ready")
    check("GET /ready reports database + auth ready", s == 200 and b["checks"]["database"] == "ok", b)

    pw = "Smoke-" + uuid.uuid4().hex[:10]
    users = []
    for label in ("A", "B"):
        email = f"smoke.{label.lower()}.{uuid.uuid4().hex[:8]}@example.com"
        s, b, _ = call(api, "POST", "/auth/register", body={"name": f"Smoke {label}", "email": email, "password": pw})
        check(f"register user {label}", s == 201 and b.get("access_token"), b)
        users.append({"email": email, "token": b.get("access_token") if isinstance(b, dict) else None})
    A, B = users

    try:
        s, b, _ = call(api, "POST", "/auth/register", body={"name": "Dup", "email": A["email"], "password": pw})
        check("duplicate registration rejected (409)", s == 409, s)
        s, b, _ = call(api, "POST", "/auth/register", body={"name": "", "email": "bad", "password": "x"})
        check("invalid registration rejected (422)", s == 422, s)
        s, b, _ = call(api, "POST", "/auth/login", body={"email": A["email"], "password": "wrong-password"})
        check("wrong password rejected (401)", s == 401, s)
        s, b, _ = call(api, "POST", "/auth/login", body={"email": A["email"].upper(), "password": pw})
        check("login (case-insensitive email)", s == 200 and b.get("access_token"), b)
        A["token"] = b["access_token"]
        s, b, _ = call(api, "GET", "/auth/me", A["token"])
        check("GET /auth/me", s == 200 and b["user"]["email"] == A["email"], b)
        s, _, _ = call(api, "GET", "/pantry")
        check("pantry without token rejected (401)", s == 401, s)
        s, _, _ = call(api, "GET", "/pantry", "not-a-real-token")
        check("pantry with forged token rejected (401)", s == 401, s)
        s, b, _ = call(api, "PATCH", "/auth/me", A["token"], {"name": "Smoke A Edited", "household_size": 3})
        check("profile update", s == 200 and b["user"]["name"] == "Smoke A Edited", b)

        soon = (date.today() + timedelta(days=2)).isoformat()
        key = uuid.uuid4().hex
        body = {"items": [{"name": "Tomatoes", "quantity": 4, "unit": "pcs", "expiry_date": soon},
                          {"name": "potato", "quantity": 1, "unit": "kg"}], "idempotency_key": key}
        s, b, t = call(api, "POST", "/pantry", A["token"], body)
        tomato = next((i for i in b if i["ingredient_id"] == "tomato"), {}) if s == 200 else {}
        potato = next((i for i in b if i["ingredient_id"] == "potato"), {}) if s == 200 else {}
        check("add pantry items", s == 200 and tomato.get("display_quantity") == "4 pcs", b if s != 200 else tomato)
        check("expiry estimated when not provided", potato.get("earliest_expiry") is not None,
              f"ai_predicted={potato.get('ai_predicted')} ({t:.1f}s)")
        s, b, _ = call(api, "POST", "/pantry", A["token"], body)
        tomato = next(i for i in b if i["ingredient_id"] == "tomato")
        check("retrying with same idempotency key does not duplicate", tomato["display_quantity"] == "4 pcs", tomato)
        s, b, _ = call(api, "PATCH", "/pantry/tomato", A["token"], {"quantity": 6, "unit": "pcs", "expiry_date": soon})
        check("edit pantry item", s == 200 and b["display_quantity"] == "6 pcs", b)
        s, b, _ = call(api, "POST", "/pantry/consume", A["token"], {"ingredient_id": "potato", "quantity": 250, "unit": "g"})
        check("consume with unit conversion", s == 200 and b["ingredient"]["display_quantity"] == "750 g", b)

        s, b, _ = call(api, "POST", "/shopping", A["token"], {"name": "Milk", "quantity": "1 l"})
        item_id = b.get("id") if isinstance(b, dict) else None
        check("add shopping item", s == 201 and item_id, b)
        s, b, _ = call(api, "PATCH", f"/shopping/{item_id}", A["token"], {"checked": True})
        check("check off shopping item", s == 200 and b["checked"] is True, b)

        s, b, _ = call(api, "POST", "/expenses", A["token"], {"title": "Smoke veg", "amount": 245.5, "category": "Vegetables"})
        exp_id = b["expense"]["id"] if s == 201 else None
        check("add expense", s == 201, b)
        s, b, _ = call(api, "GET", "/expenses", A["token"])
        check("expense summary", s == 200 and b["total_this_month"] >= 245.5, b)
        s, b, _ = call(api, "GET", "/analytics", A["token"])
        check("analytics from real data", s == 200 and b["total_pantry_items"] == 2, b)

        # ── Isolation ──
        s, b, _ = call(api, "GET", "/pantry", B["token"])
        check("user B sees an empty pantry", s == 200 and not any(i["in_stock"] for i in b), s)
        s, b, _ = call(api, "GET", "/expenses", B["token"])
        check("user B sees no expenses", s == 200 and b["expense_count"] == 0, b)
        s, _, _ = call(api, "DELETE", f"/expenses/{exp_id}", B["token"])
        check("user B cannot delete user A's expense", s == 404, s)
        s, _, _ = call(api, "PATCH", f"/shopping/{item_id}", B["token"], {"checked": False})
        check("user B cannot edit user A's shopping item", s == 404, s)
        s, _, _ = call(api, "DELETE", "/pantry/tomato", B["token"])
        check("user B cannot delete user A's pantry item", s == 404, s)

        if not a.skip_ai:
            s, b, t = call(api, "POST", "/recipes/recommend", A["token"], {"servings": 2}, timeout=150)
            ok = s == 200 and len(b.get("recipes", [])) > 0 and all(r.get("steps") for r in b["recipes"])
            check("Gemini recipe recommendations", ok, f"HTTP {s} {str(b)[:200]}")
            if ok:
                print(f"      {len(b['recipes'])} recipes in {t:.1f}s, e.g. {b['recipes'][0]['name']!r} using {b['recipes'][0]['ingredients_used']}")
            s, b, t = call(api, "GET", "/ai/insights", A["token"], timeout=90)
            check("AI insights", s == 200 and len(b.get("insights", [])) >= 3, b)
            print(f"      insights source: {b.get('source') if isinstance(b, dict) else '?'} ({t:.1f}s)")
            s, b, t = call(api, "POST", "/meals/generate", A["token"], {"days": 2}, timeout=180)
            check("Gemini meal plan", s == 200 and len(b.get("days", [])) >= 1, f"HTTP {s} {str(b)[:200]}")
            if a.receipt:
                content = open(a.receipt, "rb").read()
                s, b, t = call(api, "POST", "/receipt/process", A["token"], files=("receipt.jpg", content, "image/jpeg"), timeout=150)
                check("Gemini receipt extraction", s == 200 and b.get("items"), f"HTTP {s} {str(b)[:300]}")
                if s == 200:
                    print(f"      {len(b['items'])} items, total={b.get('total')}, date={b.get('purchase_date')}, store={b.get('store_name')!r} ({t:.1f}s)")
                    for it in b["items"][:8]:
                        print(f"        - {it['name']}: qty={it['quantity']} {it['unit'] or ''} price={it['price']}")
                    rkey = uuid.uuid4().hex
                    confirm = {"idempotency_key": rkey, "items": [{"name": i["name"], "quantity": i["quantity"] or 1, "unit": i["unit"] or "pcs"} for i in b["items"][:3]],
                               "expense": {"title": b.get("store_name") or "Receipt", "amount": b.get("total") or b.get("items_total") or 1.0}}
                    s1, _, _ = call(api, "POST", "/receipt/confirm", A["token"], confirm)
                    s2, b2, _ = call(api, "POST", "/receipt/confirm", A["token"], confirm)
                    check("receipt confirm is idempotent", s1 == 200 and s2 == 200 and b2.get("duplicate") is True, b2)

        s, b, _ = call(api, "POST", "/auth/change-password", A["token"], {"current_password": pw, "new_password": pw + "x"})
        new_token = b.get("access_token") if isinstance(b, dict) else None
        s2, _, _ = call(api, "GET", "/auth/me", A["token"])
        check("password change invalidates old session", s == 200 and s2 == 401, (s, s2))
        A["token"], A["pw"] = new_token, pw + "x"
    finally:
        for u in users:
            if u.get("token"):
                s, _, _ = call(api, "POST", "/auth/delete-account", u["token"], {"password": u.get("pw", pw)})
                check(f"delete throwaway account {u['email']}", s == 200, s)

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
