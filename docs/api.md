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
# set GARMIN_API_ENCRYPTION_KEY in .env
# recommended: set GARMIN_API_ADMIN_KEY
# set GARMIN_API_ALLOWED_HOSTS with localhost plus your public domain/IP
# optional: change GARMIN_API_PORT if 8001 is in use
```

Run locally:

```bash
export GARMIN_API_ENCRYPTION_KEY="paste-generated-key"
export GARMIN_API_ADMIN_KEY="change-this-admin-key"
export GARMIN_API_ALLOWED_HOSTS="localhost,127.0.0.1"
uvicorn garmin_api.main:app --host 0.0.0.0 --port 8001
```

Or run with Docker Compose:

```bash
docker compose up -d --build
```

## Register a Garmin Account

```bash
curl -X POST http://localhost:8001/accounts \
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
curl -X POST http://localhost:8001/accounts/mfa \
  -H "Content-Type: application/json" \
  -H "X-API-Key: account-api-key" \
  -d '{"mfa_code": "123456"}'
```

## Fetch Data

```bash
curl http://localhost:8001/summary/2026-05-13 \
  -H "X-API-Key: account-api-key"

curl http://localhost:8001/activities?start=0\&limit=20 \
  -H "X-API-Key: account-api-key"

curl http://localhost:8001/activities/latest?fresh=true \
  -H "X-API-Key: account-api-key"
```

## Interactive Docs

Open Scalar API Reference at:

```text
http://localhost:8001/docs
```

The raw OpenAPI document is available at:

```text
http://localhost:8001/openapi.json
```

Scalar shows every route, required headers, query/path parameters, request
bodies, response schemas and lets you test requests from the browser.

## Response Shape

Most data endpoints return:

```json
{
  "account_id": "internal-account-id",
  "data": {},
  "cached": false
}
```

`data` is the raw Garmin payload for that Garmin endpoint. Exact keys vary by
device, account region, enabled features and Garmin Connect+ subscription.

## Endpoints

Full route catalog with return summaries:

- [`docs/routes.md`](routes.md)

System:

- `GET /health` - returns `{"status": "ok"}`.
- `GET /docs` - Scalar interactive documentation.
- `GET /openapi.json` - generated OpenAPI schema.

Accounts:

- `POST /accounts` - requires `X-Admin-Key`; registers a Garmin account and
  returns `account_id`, `api_key`, `mfa_required` and `message`.
- `POST /accounts/mfa` - requires `X-API-Key`; completes a pending Garmin MFA
  login and returns a status message.
- `GET /me` - requires `X-API-Key`; checks whether the account can authenticate
  with Garmin.
- `GET /devices` - requires `X-API-Key`; returns devices registered to the
  Garmin account.

Daily report:

- `GET /daily-report/{date}` - requires `X-API-Key`; returns one aggregated
  report for the day with `summary`, `health`, `training`, `body`, `nutrition`
  and `warnings`. Sections that Garmin does not return are `null` and described
  in `warnings`.

Health:

- `GET /summary/{date}` - daily summary: calories, steps, distance and all-day
  totals when available.
- `GET /stats/{date}` - compatibility alias for daily summary.
- `GET /heart-rate/{date}` - daily heart-rate values and timeline.
- `GET /sleep/{date}` - sleep summary, sleep stages and sleep measurements.
- `GET /hrv/{date}` - heart-rate variability data.
- `GET /stress/{date}` - daily stress data.
- `GET /resting-heart-rate/{date}` - resting heart-rate metric.
- `GET /respiration/{date}` - respiration data.
- `GET /spo2/{date}` - blood oxygen saturation data.
- `GET /hydration/{date}` - hydration data.
- `GET /intensity-minutes/{date}` - intensity-minutes data.
- `GET /steps/{date}` - intraday step chart.
- `GET /daily-steps?start=YYYY-MM-DD&end=YYYY-MM-DD` - daily step totals for a
  range.
- `GET /floors/{date}` - floors-climbed data.

Training:

- `GET /training-readiness/{date}` - Garmin training readiness data.
- `GET /training-status/{date}` - aggregated training status.
- `GET /max-metrics/{date}` - performance max metrics such as VO2 data when
  available.
- `GET /fitness-age/{date}` - fitness-age data.
- `GET /activities?start=0&limit=20&activity_type=running` - paginated activity
  list.
- `GET /activities/latest?fresh=true` - most recent activity using
  `get_activities(0, 1)`. `fresh=true` bypasses the API cache for lightweight
  near real-time detectors.
- `GET /activities/{activity_id}` - activity summary/details.
- `GET /activities/{activity_id}/details?maxchart=2000&maxpoly=4000` - detailed
  chart and polyline payload.
- `GET /activities/{activity_id}/splits` - generic laps/splits payload.
- `GET /activities/{activity_id}/typed-splits` - sport-specific split payload.
- `GET /activities/{activity_id}/split-summaries` - summarized split blocks.
- `GET /activities/{activity_id}/weather` - Garmin weather payload for activity.
- `GET /activities/{activity_id}/hr-zones` - time in heart-rate zones.
- `GET /activities/{activity_id}/power-zones` - time in power zones.
- `GET /activities/{activity_id}/exercise-sets` - exercise sets for strength/gym
  sessions when available.
- `GET /activities/{activity_id}/download?fmt=tcx` - raw activity file. Formats:
  `original`, `tcx`, `gpx`, `kml`, `csv`.

Body:

- `GET /body-battery?start=YYYY-MM-DD&end=YYYY-MM-DD` - body battery values for
  a date or range.
- `GET /body-battery/events/{date}` - body battery events such as sleep,
  activities, auto-detected events and naps.
- `GET /body-composition?start=YYYY-MM-DD&end=YYYY-MM-DD` - weight and body
  composition range.
- `GET /stats-and-body/{date}` - daily summary merged with body-composition
  averages.
- `GET /weigh-ins?start=YYYY-MM-DD&end=YYYY-MM-DD` - weigh-ins for a range.
- `GET /weigh-ins/{date}` - weigh-ins for one day.
- `GET /blood-pressure?start=YYYY-MM-DD&end=YYYY-MM-DD` - blood-pressure
  measurements for a date or range.

Nutrition:

- `GET /nutrition/food-log/{date}` - Garmin Connect+ daily food log. Expected
  Garmin data can include consumed calories, macronutrients and logged food
  summaries when the account has nutrition tracking.
- `GET /nutrition/meals/{date}` - Garmin Connect+ meal entries for the day.
- `GET /nutrition/settings/{date}` - Garmin Connect+ calorie and macro targets
  and nutrition settings when Garmin returns them.
- `POST /nutrition/food-photo/analyze` - multipart image upload placeholder for
  Garmin Connect+ photo-based food logging. It validates `image/*` uploads and
  returns HTTP 501 until the upstream Garmin photo upload endpoint is mapped in
  this wrapper.

Garmin announced Nutrition Tracking for Garmin Connect+ on January 5, 2026. The
official Garmin newsroom says the app supports calorie and macro tracking,
daily/weekly/monthly/annual nutrition reports, barcode scanning and AI-powered
camera recognition for logging foods:
<https://www.garmin.com/en-US/newsroom/press-release/sports-fitness/stay-on-top-of-nutrition-goals-in-garmin-connect/>.
Garmin device documentation also describes Connect+ nutritional logging and
nutrition reports:
<https://www8.garmin.com/manuals/webhelp/GUID-C144B465-A0C8-4FE9-AFE6-41A3FE3F1D9A/EN-US/GUID-476303CC-9A30-4D97-B3E2-978EAE76647B.html>.

## Examples

Daily report:

```bash
curl http://localhost:8001/daily-report/2026-05-26 \
  -H "X-API-Key: account-api-key"
```

Nutrition food log:

```bash
curl http://localhost:8001/nutrition/food-log/2026-05-26 \
  -H "X-API-Key: account-api-key"
```

Food photo placeholder:

```bash
curl -X POST http://localhost:8001/nutrition/food-photo/analyze \
  -H "X-API-Key: account-api-key" \
  -F "photo=@meal.jpg;type=image/jpeg" \
  -F "meal_type=lunch" \
  -F "notes=rice, chicken and salad"
```

Expected response until Garmin photo upload is implemented:

```json
{
  "account_id": "internal-account-id",
  "status": "unsupported",
  "message": "Garmin Connect+ supports photo-based food logging in the app, but this private wrapper has no mapped Garmin upload endpoint yet.",
  "garmin_connect_plus_feature": true,
  "filename": "meal.jpg",
  "content_type": "image/jpeg",
  "meal_type": "lunch",
  "notes": "rice, chicken and salad",
  "next_steps": []
}
```

## Production Notes

- Use HTTPS on the VPS.
- Set `GARMIN_API_ADMIN_KEY`; otherwise anyone can create accounts.
- Set `GARMIN_API_ALLOWED_HOSTS` to `localhost,127.0.0.1,<your-domain>,<your-ip>`.
- Back up `your_data/garmin_api`, especially the SQLite database and token
  directories.
- Keep `GARMIN_API_ENCRYPTION_KEY` outside the repository. If it is lost, stored
  Garmin credentials cannot be decrypted.
- The API caches read calls briefly to reduce Garmin rate-limit risk.
