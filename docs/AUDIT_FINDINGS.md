# PantryPilot AI — Audit Findings (2026-10-15)

Original audit. **Status (2026-10-15): all items below have been addressed** — see README.md and docs/DEPLOYMENT.md. Remaining external steps: rotate the exposed Gemini key, deploy the backend, restrict Atlas access.

## Critical security / data isolation
- `backend/.env.example` contains what appears to be a REAL Gemini API key -> replace with placeholder, rotate key.
- No JWT_SECRET_KEY in `.env`; code falls back to a hardcoded default secret -> anyone can forge tokens. Make it required.
- Pantry routes use `get_optional_current_user` + `DEFAULT_USER_ID="default"` fallback -> unauthenticated shared pantry.
- `DELETE /api/pantry/{id}` falls back to deleting ANY doc by ObjectId or name regex with no user filter (cross-user delete).
- expenses, meals, analytics, ai/insights take `user_id` from query/body (client-supplied) -> any user can read/modify others.
- recipes/recommend always reads DEFAULT_USER inventory.
- `/api/pantry/migrate/*`, `/reset`, `/refresh-all-expiry`, `/predict-expiry`, `/receipt/process` unauthenticated.
- `connection.py`: `tlsAllowInvalidCertificates=True`; silent fallback to in-memory mongomock with a seeded demo account (Demo@123) -> data "saves" then vanishes.
- CORS `*` with credentials. Errors return `str(e)` to clients.
- Flutter stores JWT in SharedPreferences (unencrypted).

## Fabricated data presented as real
- Receipt: backend returns hash-selected fake receipts when Gemini fails; Flutter returns a hardcoded fruit list on any error.
- Recipes: hardcoded recipes when no Gemini key (backend) or network error (Flutter). MealDB overwrites Gemini instructions with a *different* dish's instructions.
- Analytics `waste_saved` invented (0.75 x stock, min 0.5 kg); Flutter fallback "2.4 kg".
- Expenses: Flutter silently "saves" to an in-memory list when backend fails.
- PantryProvider: optimistic local add on backend failure.
- Profile stats (23 items, 4.2 kg, Rs 1,200), phone/bio defaults, Settings cache/scan counts, Notifications list, Shopping list items: all hardcoded. Default user name "Ansh Yadav" baked in.
- AI insights fallback text claims "Gemini 3.8 Flash is analyzing".

## Broken / missing functionality
- Android base URL hardcoded to LAN IP `http://10.54.148.198:8000/api`; no production URL; cleartext HTTP.
- Many ApiService calls omit the Authorization header (recipes, consume, expenses, meals, analytics, insights, receipt, reset...).
- Login pushes ShellScreen on top of the auth gate -> logout leaves ShellScreen on screen. `auth.isLoading` toggled during login swaps out the login screen.
- PantryProvider created before login, never reset on logout -> previous user's data shown to next user.
- No backend profile update, no password change, no pantry item edit endpoint, no shopping-list persistence.
- Gemini model ids `gemini-3.7-flash`/`gemini-3.5-flash` not on Google's current list (stable: gemini-3.8-flash, gemini-3.6-flash, gemini-3.5-flash-lite). `google-generativeai` SDK is deprecated.
- No /health or /ready. Backend loads ultralytics model at startup (too heavy for free cloud tiers; app already does on-device inference).
- Waste "prediction" is a 4-rule threshold function (fine, but must be labelled rule-based).

## On-device detection (YOLO26s)
- `frontend/assets/models/best.onnx`: input `images [1,3,640,640]`, output `output0 [1,26,8400]`, end2end=False, 22 classes match data.yaml -> existing Dart decoder layout (cx,cy,w,h + 22 scores, NMS) is correct.
- Issues: stretch-resize instead of Ultralytics letterbox (accuracy loss on non-square photos); pixel loop + inference on UI isolate (jank); per-call no isolate.
- Model quality (test set): mAP50 ~0.61, weak classes bitter_gourd/coriander/snake_gourd/green_beans (AP50 ~0.40-0.44).
- Not yet validated: Dart pipeline vs `best.pt` predictions on real images (dataset lives on external volume).

## Mobile UI overflow sources (found by reading code)
- TopBar: Row with search + bell + unconstrained name chip, 32px side padding -> overflows on phones.
- Shopping/Profile/Settings/Pantry headers: Row(title 32px + action buttons) with no Expanded/Wrap.
- Profile: desktop Row(flex 3 / flex 5) + 4-stat Row used on mobile.
- Dashboard: 36px padding, welcome card Row with 48px emoji column, stat grid fixed aspect ratio 1.35 (overflows with large fonts).

## Environment notes
- Neither the Claude cloud workspace nor the Cowork Linux VM had internet access, so flutter/pip/Atlas/Gemini/deploy could not run there.
- Temp files `frontend/build/pylibs.tgz` and `frontend/build/pylibs2.tgz` were created for offline backend testing; safe to delete.
