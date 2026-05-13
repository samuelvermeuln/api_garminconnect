# Garmin Connect Multi-User API

This project includes a private FastAPI wrapper around the `garminconnect`
library. It supports multiple Garmin accounts by storing each account's Garmin
credentials encrypted in SQLite and keeping Garmin token files isolated per
account.

## Setup

Install the API dependencies:

```bash
pip install -e ".[api]"
```

Generate an encryption key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Create your environment:

```bash
cp .env.example .env
export GARMIN_API_ENCRYPTION_KEY="paste-generated-key"
export GARMIN_API_ADMIN_KEY="change-this-admin-key"
```

Run locally:

```bash
uvicorn garmin_api.main:app --host 0.0.0.0 --port 8000
```

Or run with Docker Compose:

```bash
docker compose up -d --build
```

## Register a Garmin Account

```bash
curl -X POST http://localhost:8000/accounts \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: change-this-admin-key" \
  -d '{
    "email": "person@example.com",
    "password": "garmin-password",
    "label": "Samuel"
  }'
```

The response includes an `api_key`. Store it securely; only its SHA-256 hash is
stored by the API.

If Garmin asks for MFA, the response has `mfa_required: true`. Complete it:

```bash
curl -X POST http://localhost:8000/accounts/mfa \
  -H "Content-Type: application/json" \
  -H "X-API-Key: account-api-key" \
  -d '{"mfa_code": "123456"}'
```

## Fetch Data

```bash
curl http://localhost:8000/summary/2026-05-13 \
  -H "X-API-Key: account-api-key"

curl http://localhost:8000/activities?start=0\&limit=20 \
  -H "X-API-Key: account-api-key"
```

Available endpoints:

- `GET /health`
- `POST /accounts`
- `POST /accounts/mfa`
- `GET /me`
- `GET /summary/{date}`
- `GET /heart-rate/{date}`
- `GET /sleep/{date}`
- `GET /hrv/{date}`
- `GET /training-readiness/{date}`
- `GET /body-battery?start=YYYY-MM-DD&end=YYYY-MM-DD`
- `GET /activities?start=0&limit=20`
- `GET /activities/{activity_id}`
- `GET /activities/{activity_id}/details`
- `GET /activities/{activity_id}/download?fmt=tcx`

## Production Notes

- Use HTTPS on the VPS.
- Set `GARMIN_API_ADMIN_KEY`; otherwise anyone can create accounts.
- Back up `your_data/garmin_api`, especially the SQLite database and token
  directories.
- Keep `GARMIN_API_ENCRYPTION_KEY` outside the repository. If it is lost, stored
  Garmin credentials cannot be decrypted.
- The API caches read calls briefly to reduce Garmin rate-limit risk.
