# Deploying PantryPilot AI

The backend is a lean FastAPI container (no PyTorch — vegetable detection runs
on the phone), so it fits free hosting tiers. These steps use **Render**; the
`backend/Dockerfile` also runs unchanged on Google Cloud Run, Fly.io, Railway
or any Docker host (it listens on `$PORT`).

## 1. Secure MongoDB Atlas first

1. **Database Access** → create a dedicated user, e.g. `pantrypilot-api`, with
   the built-in role **readWrite** on database `pantrypilot_ai` only
   (not *Atlas admin*). Use a long generated password.
2. **Network Access**: `0.0.0.0/0` is convenient during development but means
   the password is the only barrier. Render's free tier has no static outbound
   IPs, so either keep the wildcard with a strong, least-privilege user, or move
   to a host/plan with static egress IPs (Render paid, Cloud Run + Cloud NAT)
   and allow only those addresses. Atlas private endpoints require a paid tier.
3. Build the URI: `mongodb+srv://pantrypilot-api:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority`

## 2. Rotate exposed secrets

`backend/.env.example` previously contained a real-looking Gemini API key. Treat
it as exposed: revoke it in Google AI Studio → API keys, and create a new key
for production.

## 3. Put the code on GitHub

Render deploys from a Git repository. This folder is not yet a Git repo:

```bash
cd PantryAI
git init && git add . && git status   # confirm no .env / *.pt / venvs are listed
git commit -m "PantryPilot AI"
# create an empty private repo on GitHub, then:
git remote add origin git@github.com:<you>/pantrypilot-ai.git && git push -u origin main
```

`.gitignore` excludes `.env`, virtualenvs, build output and the large `.pt`
training weights. The app's model (`frontend/assets/models/best.onnx`, 38 MB)
is committed because the APK build needs it.

## 4. Create the Render service

1. Render dashboard → **New → Blueprint** → select the repo. It reads
   `render.yaml` (Docker, `backend/`, health check `/health`, free plan,
   Singapore region).
2. Enter the secret values when prompted:
   - `MONGODB_URI` — from step 1
   - `GEMINI_API_KEY` — the new key from step 2
   - `JWT_SECRET_KEY` is generated automatically by Render.
3. Deploy. When it's live, open `https://<service>.onrender.com/ready` — it
   should return `{"status":"ready", ...}`.
4. Verify end-to-end from your Mac:
   ```bash
   cd backend && python3 scripts/smoke_test.py https://<service>.onrender.com --receipt some-receipt.jpg
   ```

Free Render services sleep after 15 minutes without traffic and take up to a
minute to wake; the app pings `/health` with a long timeout before signing in
so this shows as a slower first load rather than an error. A paid instance
($7/month) stays awake.

## 5. Build the APK for that URL

```bash
cd frontend
flutter build apk --release --split-per-abi \
  --dart-define=API_URL=https://<service>.onrender.com/api
# Install on a phone connected over USB (or copy the file to the phone):
adb install -r build/app/outputs/flutter-apk/app-arm64-v8a-release.apk
```

Or, without rebuilding: open the already-installed app → **Server settings** on
the sign-in screen → enter `https://<service>.onrender.com` → *Test & save*.

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `MONGODB_URI` | yes | Atlas connection string (least-privilege user) |
| `JWT_SECRET_KEY` | yes | ≥ 32 random chars; signs session tokens |
| `GEMINI_API_KEY` | for AI features | receipts, recipes, meal plans, insights |
| `DATABASE_NAME` | no (`pantrypilot_ai`) | database name |
| `ENVIRONMENT` | no | `production` hides `/docs` |
| `GEMINI_MODELS` | no | comma-separated fallback order |
| `CORS_ORIGINS` | only for Flutter web | allowed browser origins |
| `MAX_UPLOAD_MB` | no (10) | image upload limit |

## Release signing

The APK is currently signed with the local debug key (so it can upgrade the
build already on your phone). Before publishing to the Play Store, create an
upload keystore and configure `signingConfigs.release` in
`frontend/android/app/build.gradle.kts`.
