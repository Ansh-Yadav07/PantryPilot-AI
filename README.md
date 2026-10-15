# PantryPilot AI

Your smart pantry & grocery assistant: track what's in your kitchen, catch food
before it expires, scan vegetables and receipts, plan meals, cook from what you
have, and keep an eye on grocery spending.

## Architecture

```
Flutter app (Android / desktop / web)
 ├─ On-device: YOLO26s vegetable detection (ONNX Runtime, 22 classes) — works offline
 └─ HTTPS ──► FastAPI backend (Render / any Docker host)
               ├─ MongoDB Atlas  — accounts, pantry, shopping list, expenses, meal plans
               └─ Gemini API     — receipt reading, recipes, meal plans, insights, expiry estimates
```

| Works offline (on the phone) | Needs internet (backend) |
|---|---|
| Identifying vegetables in a photo | Signing in, saving to the pantry, shopping list, expenses, meal plans |
| | Receipt reading, recipe ideas, AI insights, expiry estimates |

Secrets (MongoDB URI, Gemini key, JWT secret) exist **only** on the backend.
Every private API route requires a valid JWT and only ever touches the
signed-in user's records.

## Repository layout

- `frontend/` — Flutter app. Model: `frontend/assets/models/best.onnx` (+ `labels.json`).
- `backend/` — FastAPI API, tests (`backend/tests`), `Dockerfile`, `scripts/`.
- `ai/` — training / evaluation scripts for the vegetable detector.
- `render.yaml` — Render deployment blueprint.
- `docs/DEPLOYMENT.md` — deploying the backend and building the release APK.

## Backend — local development

```bash
cd backend
python3 -m venv .venv-api && source .venv-api/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # then fill in MONGODB_URI, GEMINI_API_KEY, JWT_SECRET_KEY
uvicorn app.main:app --reload --port 8000
```

- `GET /health` — liveness; `GET /ready` — checks MongoDB + auth configuration.
- Interactive docs at `/docs` (disabled when `ENVIRONMENT=production`).
- Tests: `pytest` (in-memory DB). Against a real cluster in a throwaway database:
  `TEST_MONGODB_URI="mongodb+srv://..." pytest`.
- End-to-end check of any running server (creates and deletes two test accounts):
  `python scripts/smoke_test.py https://your-api.onrender.com --receipt receipt.jpg`

## Flutter app

```bash
cd frontend
flutter pub get
flutter analyze && flutter test
# Development against a local backend (Android emulator reaches your Mac at 10.0.2.2):
flutter run
# Release APK pointing at the deployed backend:
flutter build apk --release --split-per-abi --dart-define=API_URL=https://your-api.onrender.com/api
```

Release builds only talk HTTPS and never fall back to localhost. An installed
app can also be pointed at a server from **Server settings** on the sign-in
screen (or Settings → Server), without rebuilding.

## Migrating data from before accounts existed

Older data was stored under a shared `default` owner. After registering, run
(dry run first, then `--apply`):

```bash
cd backend && python scripts/claim_legacy_data.py you@example.com
```
# PantryPilot-AI
