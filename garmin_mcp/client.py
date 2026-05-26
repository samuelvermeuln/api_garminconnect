"""HTTP client used by the Garmin MCP server."""

from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
from typing import Any

import requests

from .routes import ROUTES_BY_ID, RouteDoc

DEFAULT_MAX_CHARS = 12000


class GarminMcpConfigError(RuntimeError):
    """Raised when required MCP configuration is missing."""


class GarminApiRequestError(RuntimeError):
    """Raised when the Garmin HTTP API returns an error."""


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise GarminMcpConfigError(f"{name} must be an integer") from exc


class GarminApiClient:
    """Small requests-based client for the private Garmin HTTP API."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        admin_key: str | None,
        timeout_seconds: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.admin_key = admin_key
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()

    @classmethod
    def from_env(cls) -> "GarminApiClient":
        return cls(
            base_url=os.getenv("GARMIN_API_BASE_URL", "http://localhost:8000"),
            api_key=os.getenv("GARMIN_API_KEY"),
            admin_key=os.getenv("GARMIN_API_ADMIN_KEY"),
            timeout_seconds=env_int("GARMIN_MCP_TIMEOUT_SECONDS", 30),
        )

    def request_route(
        self,
        route_id: str,
        *,
        date: str | None = None,
        start: str | None = None,
        end: str | None = None,
        activity_id: str | None = None,
        fmt: str | None = None,
        activity_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        maxchart: int | None = None,
        maxpoly: int | None = None,
        body: dict[str, Any] | None = None,
        photo_path: str | None = None,
        max_chars: int = DEFAULT_MAX_CHARS,
        raw: bool = False,
    ) -> dict[str, Any]:
        route = self._get_route(route_id)
        path = self._build_path(route, date=date, activity_id=activity_id)
        url = f"{self.base_url}{path}"
        headers = self._headers(route)
        params = self._query_params(
            route,
            start=start,
            end=end,
            fmt=fmt,
            activity_type=activity_type,
            limit=limit,
            offset=offset,
            maxchart=maxchart,
            maxpoly=maxpoly,
        )

        if route.id == "nutrition.food_photo_analyze":
            return self._post_photo(
                url,
                headers=headers,
                body=body,
                photo_path=photo_path,
                max_chars=max_chars,
                raw=raw,
            )

        if route.method == "GET":
            response = self.session.get(
                url,
                headers=headers,
                params=params,
                timeout=self.timeout_seconds,
            )
        elif route.method == "POST":
            response = self.session.post(
                url,
                headers=headers,
                json=body or {},
                timeout=self.timeout_seconds,
            )
        else:
            raise GarminMcpConfigError(f"Unsupported method: {route.method}")

        return self._handle_response(
            response,
            route=route,
            max_chars=max_chars,
            raw=raw,
        )

    def _get_route(self, route_id: str) -> RouteDoc:
        route = ROUTES_BY_ID.get(route_id)
        if route is None:
            valid = ", ".join(sorted(ROUTES_BY_ID))
            raise GarminMcpConfigError(
                f"Unknown route_id '{route_id}'. Valid: {valid}"
            )
        return route

    def _headers(self, route: RouteDoc) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if route.auth == "account":
            if not self.api_key:
                raise GarminMcpConfigError("Set GARMIN_API_KEY for account routes")
            headers["X-API-Key"] = self.api_key
        elif route.auth == "admin":
            if not self.admin_key:
                raise GarminMcpConfigError(
                    "Set GARMIN_API_ADMIN_KEY for admin routes"
                )
            headers["X-Admin-Key"] = self.admin_key
        return headers

    def _build_path(
        self,
        route: RouteDoc,
        *,
        date: str | None,
        activity_id: str | None,
    ) -> str:
        path = route.path
        if "{date}" in path:
            if not date:
                raise GarminMcpConfigError(f"{route.id} requires date")
            path = path.replace("{date}", date)
        if "{activity_id}" in path:
            if not activity_id:
                raise GarminMcpConfigError(f"{route.id} requires activity_id")
            path = path.replace("{activity_id}", activity_id)
        return path

    def _query_params(
        self,
        route: RouteDoc,
        *,
        start: str | None,
        end: str | None,
        fmt: str | None,
        activity_type: str | None,
        limit: int | None,
        offset: int | None,
        maxchart: int | None,
        maxpoly: int | None,
    ) -> dict[str, str | int]:
        params: dict[str, str | int] = {}
        names = {param.name for param in route.params if param.location == "query"}
        if "start" in names:
            if not start:
                raise GarminMcpConfigError(f"{route.id} requires start")
            params["start"] = start
        if "end" in names:
            end_required = any(
                param.name == "end" and param.required for param in route.params
            )
            if end:
                params["end"] = end
            elif end_required:
                raise GarminMcpConfigError(f"{route.id} requires end")
        if "fmt" in names and fmt:
            params["fmt"] = fmt
        if "activity_type" in names and activity_type:
            params["activity_type"] = activity_type
        if route.id == "training.activities":
            params["start"] = 0 if offset is None else offset
            params["limit"] = 20 if limit is None else limit
        if "maxchart" in names:
            params["maxchart"] = 2000 if maxchart is None else maxchart
        if "maxpoly" in names:
            params["maxpoly"] = 4000 if maxpoly is None else maxpoly
        return params

    def _post_photo(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: dict[str, Any] | None,
        photo_path: str | None,
        max_chars: int,
        raw: bool,
    ) -> dict[str, Any]:
        if not photo_path:
            raise GarminMcpConfigError(
                "nutrition.food_photo_analyze requires photo_path"
            )
        path = Path(photo_path)
        if not path.is_file():
            raise GarminMcpConfigError(f"photo_path does not exist: {photo_path}")

        content_type = (
            mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        )
        data = {
            key: value
            for key, value in (body or {}).items()
            if key in {"meal_type", "notes"} and value is not None
        }
        with path.open("rb") as file_obj:
            files = {"photo": (path.name, file_obj, content_type)}
            response = self.session.post(
                url,
                headers=headers,
                data=data,
                files=files,
                timeout=self.timeout_seconds,
            )
        return self._handle_response(
            response,
            route=ROUTES_BY_ID["nutrition.food_photo_analyze"],
            max_chars=max_chars,
            raw=raw,
            allow_501=True,
        )

    def _handle_response(
        self,
        response: requests.Response,
        *,
        route: RouteDoc,
        max_chars: int,
        raw: bool,
        allow_501: bool = False,
    ) -> dict[str, Any]:
        if response.status_code >= 400 and not (
            allow_501 and response.status_code == 501
        ):
            raise GarminApiRequestError(
                f"{route.id} returned HTTP {response.status_code}: "
                f"{response.text[:1000]}"
            )

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            payload: Any = response.json()
            compact = payload if raw else limit_payload(payload, max_chars=max_chars)
            return {
                "route_id": route.id,
                "status_code": response.status_code,
                "content_type": content_type,
                "payload": compact,
            }

        text_preview = ""
        try:
            text_preview = response.text[:max_chars]
        except UnicodeDecodeError:
            text_preview = ""
        return {
            "route_id": route.id,
            "status_code": response.status_code,
            "content_type": content_type,
            "bytes": len(response.content),
            "text_preview": text_preview,
            "truncated": bool(text_preview and len(response.text) > max_chars),
        }


def limit_payload(payload: Any, *, max_chars: int) -> Any:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return payload
    return {
        "truncated": True,
        "original_chars": len(text),
        "preview_json": text[:max_chars],
        "hint": (
            "Increase max_chars or call the narrower route suggested by the docs "
            "if the LLM needs more detail."
        ),
    }
