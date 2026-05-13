"""FastAPI application for multi-user Garmin Connect access."""

from collections.abc import Callable
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

from garminconnect import Garmin

from .config import get_settings
from .schemas import (
    AccountCreateRequest,
    AccountCreateResponse,
    AccountStatusResponse,
    DataResponse,
    MfaRequest,
)
from .security import build_cipher
from .service import GarminApiError, GarminAccountService
from .store import Account, AccountStore

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
    description="Private API for accessing Garmin Connect data from multiple accounts.",
)


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


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    if settings.admin_key and x_admin_key != settings.admin_key:
        raise HTTPException(status_code=401, detail="invalid admin key")


def current_account(x_api_key: str = Header()) -> Account:
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/accounts",
    response_model=AccountCreateResponse,
    dependencies=[Depends(require_admin)],
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


@app.post("/accounts/mfa")
def complete_mfa(
    payload: MfaRequest,
    account: Account = Depends(current_account),
) -> dict[str, str]:
    service.complete_mfa(account, payload.mfa_code)
    return {"status": "ok", "message": "MFA completed and Garmin tokens saved."}


@app.get("/me", response_model=AccountStatusResponse)
def me(account: Account = Depends(current_account)) -> AccountStatusResponse:
    service.login_account(account)
    return AccountStatusResponse(
        account_id=account.id,
        label=account.label,
        authenticated=True,
    )


@app.get("/summary/{date}", response_model=DataResponse)
def summary(date: str, account: Account = Depends(current_account)) -> DataResponse:
    return cached_data(
        account,
        ("summary", date),
        lambda garmin: garmin.get_user_summary(date),
    )


@app.get("/heart-rate/{date}", response_model=DataResponse)
def heart_rate(date: str, account: Account = Depends(current_account)) -> DataResponse:
    return cached_data(
        account,
        ("heart-rate", date),
        lambda garmin: garmin.get_heart_rates(date),
    )


@app.get("/sleep/{date}", response_model=DataResponse)
def sleep(date: str, account: Account = Depends(current_account)) -> DataResponse:
    return cached_data(
        account,
        ("sleep", date),
        lambda garmin: garmin.get_sleep_data(date),
    )


@app.get("/hrv/{date}", response_model=DataResponse)
def hrv(date: str, account: Account = Depends(current_account)) -> DataResponse:
    return cached_data(
        account,
        ("hrv", date),
        lambda garmin: garmin.get_hrv_data(date),
    )


@app.get("/training-readiness/{date}", response_model=DataResponse)
def training_readiness(
    date: str, account: Account = Depends(current_account)
) -> DataResponse:
    return cached_data(
        account,
        ("training-readiness", date),
        lambda garmin: garmin.get_training_readiness(date),
    )


@app.get("/body-battery", response_model=DataResponse)
def body_battery(
    start: str,
    end: str | None = None,
    account: Account = Depends(current_account),
) -> DataResponse:
    return cached_data(
        account,
        ("body-battery", start, end),
        lambda garmin: garmin.get_body_battery(start, end),
    )


@app.get("/activities", response_model=DataResponse)
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


@app.get("/activities/{activity_id}", response_model=DataResponse)
def activity(
    activity_id: str, account: Account = Depends(current_account)
) -> DataResponse:
    return cached_data(
        account,
        ("activity", activity_id),
        lambda garmin: garmin.get_activity(activity_id),
    )


@app.get("/activities/{activity_id}/details", response_model=DataResponse)
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


@app.get("/activities/{activity_id}/download")
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
