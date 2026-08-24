"""FastAPI application for multi-user Garmin Connect access."""

from collections.abc import Callable
from typing import Any, Literal

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Security,
    UploadFile,
)
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.security import APIKeyHeader
from starlette.middleware.trustedhost import TrustedHostMiddleware

from garminconnect import (
    Garmin,
    GarminConnectConnectionError,
)

from .config import get_settings
from .schemas import (
    AccountCreateRequest,
    AccountCreateResponse,
    AccountStatusResponse,
    DataResponse,
    DailyReportResponse,
    FoodPhotoAnalysisResponse,
    MfaRequest,
)
from .security import build_cipher
from .service import GarminApiError, GarminAccountService
from .store import Account, AccountStore

DATE_DESCRIPTION = "Date in YYYY-MM-DD format."

OPENAPI_TAGS = [
    {
        "name": "system",
        "description": "Healthcheck and interactive API documentation.",
    },
    {
        "name": "accounts",
        "description": "Account registration, MFA and Garmin login status.",
    },
    {
        "name": "daily report",
        "description": "Aggregated daily health, training, body and nutrition report.",
    },
    {
        "name": "health",
        "description": "Daily health metrics from Garmin Connect.",
    },
    {
        "name": "training",
        "description": "Training readiness, activities and performance metrics.",
    },
    {
        "name": "body",
        "description": "Body composition, weigh-ins and body battery.",
    },
    {
        "name": "nutrition",
        "description": (
            "Garmin Connect+ nutrition data where available, including the "
            "documented experimental food photo workflow."
        ),
    },
]

API_KEY_RESPONSES = {
    401: {"description": "Invalid X-API-Key or Garmin authentication failure."},
    429: {"description": "Garmin rate limit reached."},
    502: {"description": "Garmin Connect communication error."},
}

ADMIN_KEY_RESPONSES = {
    401: {"description": "Invalid X-Admin-Key."},
}

api_key_header = APIKeyHeader(name="X-API-Key", scheme_name="AccountApiKey")
admin_key_header = APIKeyHeader(
    name="X-Admin-Key",
    scheme_name="AdminApiKey",
    auto_error=False,
)

settings = get_settings()
store = AccountStore(settings.database_path)
service = GarminAccountService(
    store=store,
    cipher=build_cipher(settings.encryption_key),
    storage_path=settings.storage_path,
    cache_ttl_seconds=settings.cache_ttl_seconds,
)

app = FastAPI(
    title="Garmin Connect Multi-User API",
    version="0.1.0",
    description=(
        "Private API for accessing Garmin Connect data from multiple accounts. "
        "Use X-Admin-Key only for account creation and X-API-Key for account data."
    ),
    docs_url=None,
    redoc_url=None,
    openapi_tags=OPENAPI_TAGS,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)


@app.exception_handler(GarminApiError)
async def garmin_api_error_handler(
    _request: Request, exc: GarminApiError
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc)},
    )


@app.exception_handler(ValueError)
async def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def require_admin(x_admin_key: str | None = Security(admin_key_header)) -> None:
    if settings.admin_key and x_admin_key != settings.admin_key:
        raise HTTPException(status_code=401, detail="invalid admin key")


def current_account(x_api_key: str = Security(api_key_header)) -> Account:
    return service.authenticate_account(x_api_key)


def cached_data(
    account: Account,
    cache_key: tuple[Any, ...],
    fetcher: Callable[[Garmin], Any],
) -> DataResponse:
    def load() -> Any:
        garmin = service.get_garmin(account)
        return fetcher(garmin)

    data, cached = service.cached_call(account, cache_key, load)
    return DataResponse(account_id=account.id, data=data, cached=cached)


@app.get("/docs", include_in_schema=False)
def scalar_docs() -> HTMLResponse:
    return HTMLResponse(
        """
<!doctype html>
<html>
  <head>
    <title>Garmin Connect API Docs</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      body { margin: 0; }
    </style>
  </head>
  <body>
    <script
      id="api-reference"
      data-url="/openapi.json"
      data-configuration='{"theme":"default","layout":"modern"}'>
    </script>
    <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
  </body>
</html>
        """.strip()
    )


@app.get(
    "/health",
    tags=["system"],
    summary="Check API health",
    description="Returns a small status payload when the FastAPI process is alive.",
)
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/accounts",
    response_model=AccountCreateResponse,
    dependencies=[Depends(require_admin)],
    tags=["accounts"],
    summary="Register a Garmin account",
    description=(
        "Creates an internal account, stores Garmin credentials encrypted in SQLite, "
        "attempts Garmin login and returns the account X-API-Key. Send X-Admin-Key."
    ),
    responses=ADMIN_KEY_RESPONSES,
)
def create_account(payload: AccountCreateRequest) -> AccountCreateResponse:
    account, api_key, mfa_required = service.create_account(
        email=payload.email,
        password=payload.password,
        label=payload.label,
        is_cn=payload.is_cn,
    )
    message = (
        "Garmin requested MFA. Send the code to /accounts/mfa with this API key."
        if mfa_required
        else "Account created and Garmin login completed."
    )
    return AccountCreateResponse(
        account_id=account.id,
        api_key=api_key,
        mfa_required=mfa_required,
        message=message,
    )


@app.post(
    "/accounts/mfa",
    tags=["accounts"],
    summary="Complete Garmin MFA",
    description=(
        "Completes a pending Garmin MFA login using the X-API-Key returned by "
        "POST /accounts."
    ),
    responses=API_KEY_RESPONSES,
)
def complete_mfa(
    payload: MfaRequest,
    account: Account = Depends(current_account),
) -> dict[str, str]:
    service.complete_mfa(account, payload.mfa_code)
    return {"status": "ok", "message": "MFA completed and Garmin tokens saved."}


@app.get(
    "/me",
    response_model=AccountStatusResponse,
    tags=["accounts"],
    summary="Check authenticated Garmin account",
    description=(
        "Validates the X-API-Key and verifies Garmin login/token refresh for the "
        "current account."
    ),
    responses=API_KEY_RESPONSES,
)
def me(account: Account = Depends(current_account)) -> AccountStatusResponse:
    service.login_account(account)
    return AccountStatusResponse(
        account_id=account.id,
        label=account.label,
        authenticated=True,
    )


def _collect_report_section(
    warnings: list[str],
    name: str,
    fetcher: Callable[[], Any],
) -> Any | None:
    try:
        return fetcher()
    except GarminConnectConnectionError as err:
        warnings.append(f"{name}: {err}")
        return None


def _build_daily_report(account: Account, date: str) -> DailyReportResponse:
    def load() -> dict[str, Any]:
        garmin = service.get_garmin(account)
        warnings: list[str] = []
        summary = _collect_report_section(
            warnings,
            "summary",
            lambda: garmin.get_user_summary(date),
        )
        health = {
            "heart_rate": _collect_report_section(
                warnings, "heart_rate", lambda: garmin.get_heart_rates(date)
            ),
            "sleep": _collect_report_section(
                warnings, "sleep", lambda: garmin.get_sleep_data(date)
            ),
            "hrv": _collect_report_section(
                warnings, "hrv", lambda: garmin.get_hrv_data(date)
            ),
            "body_battery": _collect_report_section(
                warnings, "body_battery", lambda: garmin.get_body_battery(date)
            ),
            "body_battery_events": _collect_report_section(
                warnings,
                "body_battery_events",
                lambda: garmin.get_body_battery_events(date),
            ),
            "stress": _collect_report_section(
                warnings, "stress", lambda: garmin.get_stress_data(date)
            ),
            "respiration": _collect_report_section(
                warnings, "respiration", lambda: garmin.get_respiration_data(date)
            ),
            "spo2": _collect_report_section(
                warnings, "spo2", lambda: garmin.get_spo2_data(date)
            ),
            "hydration": _collect_report_section(
                warnings, "hydration", lambda: garmin.get_hydration_data(date)
            ),
            "intensity_minutes": _collect_report_section(
                warnings,
                "intensity_minutes",
                lambda: garmin.get_intensity_minutes_data(date),
            ),
            "resting_heart_rate": _collect_report_section(
                warnings, "resting_heart_rate", lambda: garmin.get_rhr_day(date)
            ),
        }
        training = {
            "training_readiness": _collect_report_section(
                warnings,
                "training_readiness",
                lambda: garmin.get_training_readiness(date),
            ),
            "training_status": _collect_report_section(
                warnings, "training_status", lambda: garmin.get_training_status(date)
            ),
            "max_metrics": _collect_report_section(
                warnings, "max_metrics", lambda: garmin.get_max_metrics(date)
            ),
            "fitness_age": _collect_report_section(
                warnings, "fitness_age", lambda: garmin.get_fitnessage_data(date)
            ),
            "recent_activities": _collect_report_section(
                warnings,
                "recent_activities",
                lambda: garmin.get_activities(0, 10),
            ),
        }
        body = {
            "composition": _collect_report_section(
                warnings, "body_composition", lambda: garmin.get_body_composition(date)
            ),
            "weigh_ins": _collect_report_section(
                warnings, "weigh_ins", lambda: garmin.get_daily_weigh_ins(date)
            ),
            "blood_pressure": _collect_report_section(
                warnings, "blood_pressure", lambda: garmin.get_blood_pressure(date)
            ),
        }
        nutrition = {
            "food_log": _collect_report_section(
                warnings,
                "nutrition_food_log",
                lambda: garmin.get_nutrition_daily_food_log(date),
            ),
            "meals": _collect_report_section(
                warnings,
                "nutrition_meals",
                lambda: garmin.get_nutrition_daily_meals(date),
            ),
            "settings": _collect_report_section(
                warnings,
                "nutrition_settings",
                lambda: garmin.get_nutrition_daily_settings(date),
            ),
        }
        return {
            "summary": summary,
            "health": health,
            "training": training,
            "body": body,
            "nutrition": nutrition,
            "warnings": warnings,
        }

    data, cached = service.cached_call(account, ("daily-report", date), load)
    return DailyReportResponse(
        account_id=account.id,
        date=date,
        cached=cached,
        summary=data["summary"],
        health=data["health"],
        training=data["training"],
        body=data["body"],
        nutrition=data["nutrition"],
        warnings=data["warnings"],
    )


@app.get(
    "/daily-report/{date}",
    response_model=DailyReportResponse,
    tags=["daily report"],
    summary="Get complete daily report",
    description=(
        "Builds a single daily report with Garmin summary, health metrics, "
        "training metrics, body composition and Garmin Connect+ nutrition data. "
        "Sections that are unavailable return null and add a warning."
    ),
    responses=API_KEY_RESPONSES,
)
def daily_report(
    date: str,
    account: Account = Depends(current_account),
) -> DailyReportResponse:
    return _build_daily_report(account, date)


@app.get(
    "/summary/{date}",
    response_model=DataResponse,
    tags=["health"],
    summary="Get daily summary",
    description=(
        "Returns Garmin daily user summary for the date, including common fields "
        "such as totalKilocalories, activeKilocalories, consumedKilocalories, "
        "remainingKilocalories, totalSteps, totalDistanceMeters and intensity data "
        "when Garmin provides them."
    ),
    responses=API_KEY_RESPONSES,
)
def summary(date: str, account: Account = Depends(current_account)) -> DataResponse:
    return cached_data(
        account,
        ("summary", date),
        lambda garmin: garmin.get_user_summary(date),
    )


@app.get(
    "/stats/{date}",
    response_model=DataResponse,
    tags=["health"],
    summary="Get compatibility daily stats",
    description=(
        "Compatibility alias for the Garmin daily summary returned by "
        "garmin.get_stats(date)."
    ),
    responses=API_KEY_RESPONSES,
)
def stats(date: str, account: Account = Depends(current_account)) -> DataResponse:
    return cached_data(
        account,
        ("stats", date),
        lambda garmin: garmin.get_stats(date),
    )


@app.get(
    "/stats-and-body/{date}",
    response_model=DataResponse,
    tags=["body"],
    summary="Get daily stats merged with body composition",
    description=(
        "Returns daily summary fields merged with the daily body-composition "
        "average when Garmin has weight/body data for the date."
    ),
    responses=API_KEY_RESPONSES,
)
def stats_and_body(
    date: str, account: Account = Depends(current_account)
) -> DataResponse:
    return cached_data(
        account,
        ("stats-and-body", date),
        lambda garmin: garmin.get_stats_and_body(date),
    )


@app.get(
    "/heart-rate/{date}",
    response_model=DataResponse,
    tags=["health"],
    summary="Get daily heart-rate timeline",
    description=(
        "Returns the Garmin heart-rate data for the date, usually including "
        "restingHeartRate, min/max values and intraday heart-rate samples."
    ),
    responses=API_KEY_RESPONSES,
)
def heart_rate(date: str, account: Account = Depends(current_account)) -> DataResponse:
    return cached_data(
        account,
        ("heart-rate", date),
        lambda garmin: garmin.get_heart_rates(date),
    )


@app.get(
    "/sleep/{date}",
    response_model=DataResponse,
    tags=["health"],
    summary="Get sleep data",
    description=(
        "Returns Garmin sleep data for the date, including sleep summary, stages "
        "and related measurements when available."
    ),
    responses=API_KEY_RESPONSES,
)
def sleep(date: str, account: Account = Depends(current_account)) -> DataResponse:
    return cached_data(
        account,
        ("sleep", date),
        lambda garmin: garmin.get_sleep_data(date),
    )


@app.get(
    "/hrv/{date}",
    response_model=DataResponse,
    tags=["health"],
    summary="Get HRV data",
    description="Returns heart-rate variability data for the requested date.",
    responses=API_KEY_RESPONSES,
)
def hrv(date: str, account: Account = Depends(current_account)) -> DataResponse:
    return cached_data(
        account,
        ("hrv", date),
        lambda garmin: garmin.get_hrv_data(date),
    )


@app.get(
    "/stress/{date}",
    response_model=DataResponse,
    tags=["health"],
    summary="Get daily stress",
    description="Returns Garmin daily stress data and timeline values.",
    responses=API_KEY_RESPONSES,
)
def stress(date: str, account: Account = Depends(current_account)) -> DataResponse:
    return cached_data(
        account,
        ("stress", date),
        lambda garmin: garmin.get_stress_data(date),
    )


@app.get(
    "/resting-heart-rate/{date}",
    response_model=DataResponse,
    tags=["health"],
    summary="Get resting heart rate",
    description="Returns Garmin resting heart-rate metric for the requested date.",
    responses=API_KEY_RESPONSES,
)
def resting_heart_rate(
    date: str, account: Account = Depends(current_account)
) -> DataResponse:
    return cached_data(
        account,
        ("resting-heart-rate", date),
        lambda garmin: garmin.get_rhr_day(date),
    )


@app.get(
    "/respiration/{date}",
    response_model=DataResponse,
    tags=["health"],
    summary="Get respiration data",
    description="Returns Garmin respiration data for the requested date.",
    responses=API_KEY_RESPONSES,
)
def respiration(date: str, account: Account = Depends(current_account)) -> DataResponse:
    return cached_data(
        account,
        ("respiration", date),
        lambda garmin: garmin.get_respiration_data(date),
    )


@app.get(
    "/spo2/{date}",
    response_model=DataResponse,
    tags=["health"],
    summary="Get SpO2 data",
    description="Returns Garmin blood oxygen saturation data for the requested date.",
    responses=API_KEY_RESPONSES,
)
def spo2(date: str, account: Account = Depends(current_account)) -> DataResponse:
    return cached_data(
        account,
        ("spo2", date),
        lambda garmin: garmin.get_spo2_data(date),
    )


@app.get(
    "/hydration/{date}",
    response_model=DataResponse,
    tags=["health"],
    summary="Get hydration data",
    description="Returns Garmin hydration data for the requested date.",
    responses=API_KEY_RESPONSES,
)
def hydration(date: str, account: Account = Depends(current_account)) -> DataResponse:
    return cached_data(
        account,
        ("hydration", date),
        lambda garmin: garmin.get_hydration_data(date),
    )


@app.get(
    "/intensity-minutes/{date}",
    response_model=DataResponse,
    tags=["health"],
    summary="Get intensity minutes",
    description="Returns Garmin intensity-minute data for the requested date.",
    responses=API_KEY_RESPONSES,
)
def intensity_minutes(
    date: str, account: Account = Depends(current_account)
) -> DataResponse:
    return cached_data(
        account,
        ("intensity-minutes", date),
        lambda garmin: garmin.get_intensity_minutes_data(date),
    )


@app.get(
    "/steps/{date}",
    response_model=DataResponse,
    tags=["health"],
    summary="Get intraday steps",
    description="Returns Garmin step chart data for the requested date.",
    responses=API_KEY_RESPONSES,
)
def steps(date: str, account: Account = Depends(current_account)) -> DataResponse:
    return cached_data(
        account,
        ("steps", date),
        lambda garmin: garmin.get_steps_data(date),
    )


@app.get(
    "/daily-steps",
    response_model=DataResponse,
    tags=["health"],
    summary="Get daily steps range",
    description=(
        "Returns daily step totals between start and end. Garmin limits each "
        "underlying request to 28 days; the wrapper chunks longer ranges."
    ),
    responses=API_KEY_RESPONSES,
)
def daily_steps(
    start: str = Query(description=DATE_DESCRIPTION),
    end: str = Query(description=DATE_DESCRIPTION),
    account: Account = Depends(current_account),
) -> DataResponse:
    return cached_data(
        account,
        ("daily-steps", start, end),
        lambda garmin: garmin.get_daily_steps(start, end),
    )


@app.get(
    "/floors/{date}",
    response_model=DataResponse,
    tags=["health"],
    summary="Get floors climbed",
    description="Returns Garmin floors-climbed chart data for the requested date.",
    responses=API_KEY_RESPONSES,
)
def floors(date: str, account: Account = Depends(current_account)) -> DataResponse:
    return cached_data(
        account,
        ("floors", date),
        lambda garmin: garmin.get_floors(date),
    )


@app.get(
    "/training-readiness/{date}",
    response_model=DataResponse,
    tags=["training"],
    summary="Get training readiness",
    description="Returns Garmin training readiness data for the requested date.",
    responses=API_KEY_RESPONSES,
)
def training_readiness(
    date: str, account: Account = Depends(current_account)
) -> DataResponse:
    return cached_data(
        account,
        ("training-readiness", date),
        lambda garmin: garmin.get_training_readiness(date),
    )


@app.get(
    "/training-status/{date}",
    response_model=DataResponse,
    tags=["training"],
    summary="Get training status",
    description="Returns Garmin aggregated training status for the requested date.",
    responses=API_KEY_RESPONSES,
)
def training_status(
    date: str, account: Account = Depends(current_account)
) -> DataResponse:
    return cached_data(
        account,
        ("training-status", date),
        lambda garmin: garmin.get_training_status(date),
    )


@app.get(
    "/max-metrics/{date}",
    response_model=DataResponse,
    tags=["training"],
    summary="Get max performance metrics",
    description="Returns Garmin max metrics for the requested date, such as VO2 data.",
    responses=API_KEY_RESPONSES,
)
def max_metrics(date: str, account: Account = Depends(current_account)) -> DataResponse:
    return cached_data(
        account,
        ("max-metrics", date),
        lambda garmin: garmin.get_max_metrics(date),
    )


@app.get(
    "/fitness-age/{date}",
    response_model=DataResponse,
    tags=["training"],
    summary="Get fitness age",
    description="Returns Garmin fitness-age data for the requested date.",
    responses=API_KEY_RESPONSES,
)
def fitness_age(date: str, account: Account = Depends(current_account)) -> DataResponse:
    return cached_data(
        account,
        ("fitness-age", date),
        lambda garmin: garmin.get_fitnessage_data(date),
    )


@app.get(
    "/body-battery",
    response_model=DataResponse,
    tags=["body"],
    summary="Get body battery range",
    description=(
        "Returns Garmin body battery values from start through end. If end is "
        "omitted, only the start date is returned."
    ),
    responses=API_KEY_RESPONSES,
)
def body_battery(
    start: str = Query(description=DATE_DESCRIPTION),
    end: str | None = Query(default=None, description=DATE_DESCRIPTION),
    account: Account = Depends(current_account),
) -> DataResponse:
    return cached_data(
        account,
        ("body-battery", start, end),
        lambda garmin: garmin.get_body_battery(start, end),
    )


@app.get(
    "/body-battery/events/{date}",
    response_model=DataResponse,
    tags=["body"],
    summary="Get body battery events",
    description=(
        "Returns Garmin body battery events for a date, such as sleep, activities, "
        "auto-detected events and naps when Garmin provides them."
    ),
    responses=API_KEY_RESPONSES,
)
def body_battery_events(
    date: str, account: Account = Depends(current_account)
) -> DataResponse:
    return cached_data(
        account,
        ("body-battery-events", date),
        lambda garmin: garmin.get_body_battery_events(date),
    )


@app.get(
    "/body-composition",
    response_model=DataResponse,
    tags=["body"],
    summary="Get body composition range",
    description=(
        "Returns weight and body-composition data from Garmin between start and "
        "end. If end is omitted, only the start date is returned."
    ),
    responses=API_KEY_RESPONSES,
)
def body_composition(
    start: str = Query(description=DATE_DESCRIPTION),
    end: str | None = Query(default=None, description=DATE_DESCRIPTION),
    account: Account = Depends(current_account),
) -> DataResponse:
    return cached_data(
        account,
        ("body-composition", start, end),
        lambda garmin: garmin.get_body_composition(start, end),
    )


@app.get(
    "/weigh-ins",
    response_model=DataResponse,
    tags=["body"],
    summary="Get weigh-ins range",
    description="Returns Garmin weigh-ins between start and end dates.",
    responses=API_KEY_RESPONSES,
)
def weigh_ins(
    start: str = Query(description=DATE_DESCRIPTION),
    end: str = Query(description=DATE_DESCRIPTION),
    account: Account = Depends(current_account),
) -> DataResponse:
    return cached_data(
        account,
        ("weigh-ins", start, end),
        lambda garmin: garmin.get_weigh_ins(start, end),
    )


@app.get(
    "/weigh-ins/{date}",
    response_model=DataResponse,
    tags=["body"],
    summary="Get daily weigh-ins",
    description="Returns Garmin weigh-ins for a single date.",
    responses=API_KEY_RESPONSES,
)
def daily_weigh_ins(
    date: str, account: Account = Depends(current_account)
) -> DataResponse:
    return cached_data(
        account,
        ("daily-weigh-ins", date),
        lambda garmin: garmin.get_daily_weigh_ins(date),
    )


@app.get(
    "/blood-pressure",
    response_model=DataResponse,
    tags=["body"],
    summary="Get blood pressure range",
    description=(
        "Returns Garmin blood-pressure measurements between start and end. If end "
        "is omitted, only the start date is returned."
    ),
    responses=API_KEY_RESPONSES,
)
def blood_pressure(
    start: str = Query(description=DATE_DESCRIPTION),
    end: str | None = Query(default=None, description=DATE_DESCRIPTION),
    account: Account = Depends(current_account),
) -> DataResponse:
    return cached_data(
        account,
        ("blood-pressure", start, end),
        lambda garmin: garmin.get_blood_pressure(start, end),
    )


@app.get(
    "/devices",
    response_model=DataResponse,
    tags=["accounts"],
    summary="List Garmin devices",
    description="Returns Garmin devices registered to the authenticated account.",
    responses=API_KEY_RESPONSES,
)
def devices(account: Account = Depends(current_account)) -> DataResponse:
    return cached_data(
        account,
        ("devices",),
        lambda garmin: garmin.get_devices(),
    )


@app.get(
    "/nutrition/food-log/{date}",
    response_model=DataResponse,
    tags=["nutrition"],
    summary="Get nutrition food log",
    description=(
        "Returns the Garmin Connect+ daily food log for the date when nutrition "
        "tracking is available on the account. This can include consumed calories, "
        "macros and logged food summaries depending on Garmin's response."
    ),
    responses=API_KEY_RESPONSES,
)
def nutrition_food_log(
    date: str, account: Account = Depends(current_account)
) -> DataResponse:
    return cached_data(
        account,
        ("nutrition-food-log", date),
        lambda garmin: garmin.get_nutrition_daily_food_log(date),
    )


@app.get(
    "/nutrition/meals/{date}",
    response_model=DataResponse,
    tags=["nutrition"],
    summary="Get nutrition meals",
    description=(
        "Returns Garmin Connect+ meal entries for the date when nutrition tracking "
        "is available on the account."
    ),
    responses=API_KEY_RESPONSES,
)
def nutrition_meals(
    date: str, account: Account = Depends(current_account)
) -> DataResponse:
    return cached_data(
        account,
        ("nutrition-meals", date),
        lambda garmin: garmin.get_nutrition_daily_meals(date),
    )


@app.get(
    "/nutrition/settings/{date}",
    response_model=DataResponse,
    tags=["nutrition"],
    summary="Get nutrition settings",
    description=(
        "Returns Garmin Connect+ nutrition settings and targets for the date, "
        "including calorie and macronutrient goals when Garmin provides them."
    ),
    responses=API_KEY_RESPONSES,
)
def nutrition_settings(
    date: str, account: Account = Depends(current_account)
) -> DataResponse:
    return cached_data(
        account,
        ("nutrition-settings", date),
        lambda garmin: garmin.get_nutrition_daily_settings(date),
    )


@app.post(
    "/nutrition/food-photo/analyze",
    response_model=FoodPhotoAnalysisResponse,
    status_code=501,
    tags=["nutrition"],
    summary="Analyze a food photo",
    description=(
        "Experimental placeholder for Garmin Connect+ photo-based food logging. "
        "Garmin documents AI image recognition in the Garmin Connect app, but this "
        "wrapper does not yet include a public/mapped Garmin endpoint for uploading "
        "meal photos. The route accepts multipart image uploads so clients can be "
        "built against the future contract, then returns 501 until the upstream "
        "endpoint is implemented."
    ),
    responses={
        **API_KEY_RESPONSES,
        400: {"description": "The uploaded file is not an image."},
        501: {
            "description": (
                "Food-photo analysis is documented but not implemented in this API."
            )
        },
    },
)
async def analyze_food_photo(
    photo: UploadFile = File(
        description="Food image to analyze. Use image/jpeg, image/png or image/webp."
    ),
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"] | None = Form(
        default=None,
        description="Optional meal category.",
    ),
    notes: str | None = Form(
        default=None,
        description="Optional context, portion estimate or ingredients.",
    ),
    account: Account = Depends(current_account),
) -> JSONResponse:
    if not photo.content_type or not photo.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="photo must be an image/* upload")

    payload = FoodPhotoAnalysisResponse(
        account_id=account.id,
        status="unsupported",
        message=(
            "Garmin Connect+ supports photo-based food logging in the app, but this "
            "private wrapper has no mapped Garmin upload endpoint yet."
        ),
        garmin_connect_plus_feature=True,
        filename=photo.filename,
        content_type=photo.content_type,
        meal_type=meal_type,
        notes=notes,
        next_steps=[
            "Map the Garmin Connect nutrition photo upload endpoint when available.",
            "Send the image bytes to that endpoint with the authenticated Garmin session.",
            "Normalize Garmin's estimate into calories, protein, carbs, fat and feedback.",
        ],
    )
    return JSONResponse(status_code=501, content=payload.model_dump())


@app.get(
    "/activities",
    response_model=DataResponse,
    tags=["training"],
    summary="List activities",
    description=(
        "Returns recent Garmin activities. Use start for pagination offset, limit "
        "for page size and activity_type for Garmin activity type filtering."
    ),
    responses=API_KEY_RESPONSES,
)
def activities(
    start: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    activity_type: str | None = None,
    account: Account = Depends(current_account),
) -> DataResponse:
    return cached_data(
        account,
        ("activities", start, limit, activity_type),
        lambda garmin: garmin.get_activities(start, limit, activity_type),
    )


@app.get(
    "/activities/{activity_id}",
    response_model=DataResponse,
    tags=["training"],
    summary="Get activity summary",
    description="Returns Garmin summary/details for a single activity id.",
    responses=API_KEY_RESPONSES,
)
def activity(
    activity_id: str, account: Account = Depends(current_account)
) -> DataResponse:
    return cached_data(
        account,
        ("activity", activity_id),
        lambda garmin: garmin.get_activity(activity_id),
    )


@app.get(
    "/activities/{activity_id}/details",
    response_model=DataResponse,
    tags=["training"],
    summary="Get activity chart details",
    description=(
        "Returns detailed Garmin activity data, including chart samples and "
        "polyline data when Garmin provides it. maxchart and maxpoly control "
        "payload size."
    ),
    responses=API_KEY_RESPONSES,
)
def activity_details(
    activity_id: str,
    maxchart: int = Query(default=2000, ge=1),
    maxpoly: int = Query(default=4000, ge=0),
    account: Account = Depends(current_account),
) -> DataResponse:
    return cached_data(
        account,
        ("activity-details", activity_id, maxchart, maxpoly),
        lambda garmin: garmin.get_activity_details(activity_id, maxchart, maxpoly),
    )


@app.get(
    "/activities/{activity_id}/download",
    tags=["training"],
    summary="Download activity file",
    description=(
        "Downloads an activity file from Garmin in original, TCX, GPX, KML or CSV "
        "format. The response body is the raw file content."
    ),
    responses={
        **API_KEY_RESPONSES,
        200: {"description": "Raw activity file content."},
    },
)
def download_activity(
    activity_id: str,
    fmt: Literal["original", "tcx", "gpx", "kml", "csv"] = "tcx",
    account: Account = Depends(current_account),
) -> Response:
    formats = {
        "original": Garmin.ActivityDownloadFormat.ORIGINAL,
        "tcx": Garmin.ActivityDownloadFormat.TCX,
        "gpx": Garmin.ActivityDownloadFormat.GPX,
        "kml": Garmin.ActivityDownloadFormat.KML,
        "csv": Garmin.ActivityDownloadFormat.CSV,
    }
    garmin = service.get_garmin(account)
    download_format = formats[fmt]
    content = garmin.download_activity(activity_id, download_format)
    media_types = {
        Garmin.ActivityDownloadFormat.ORIGINAL: "application/zip",
        Garmin.ActivityDownloadFormat.TCX: "application/xml",
        Garmin.ActivityDownloadFormat.GPX: "application/gpx+xml",
        Garmin.ActivityDownloadFormat.KML: "application/vnd.google-earth.kml+xml",
        Garmin.ActivityDownloadFormat.CSV: "text/csv",
    }
    return Response(content=content, media_type=media_types[download_format])
