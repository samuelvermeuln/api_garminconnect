"""Route contracts used by the Garmin MCP server."""

from dataclasses import dataclass, field
from typing import Literal

AuthKind = Literal["none", "admin", "account"]
ParamLocation = Literal["path", "query", "body", "form"]


@dataclass(frozen=True)
class ParamDoc:
    name: str
    location: ParamLocation
    required: bool
    description: str
    example: str | int | bool | None = None


@dataclass(frozen=True)
class RouteDoc:
    id: str
    method: Literal["GET", "POST"]
    path: str
    category: str
    auth: AuthKind
    summary: str
    returns: str
    params: tuple[ParamDoc, ...] = ()
    response_contract: str = (
        "JSON response. Most data endpoints return "
        "{account_id: string, data: Garmin raw payload, cached: boolean}."
    )
    example: str = ""
    keywords: tuple[str, ...] = field(default_factory=tuple)

    def compact(self) -> dict[str, object]:
        return {
            "id": self.id,
            "method": self.method,
            "path": self.path,
            "category": self.category,
            "auth": self.auth,
            "summary": self.summary,
            "returns": self.returns,
            "required_params": [
                param.name for param in self.params if param.required
            ],
        }

    def full_contract(self) -> dict[str, object]:
        return {
            **self.compact(),
            "params": [
                {
                    "name": param.name,
                    "in": param.location,
                    "required": param.required,
                    "description": param.description,
                    "example": param.example,
                }
                for param in self.params
            ],
            "response_contract": self.response_contract,
            "example": self.example,
            "keywords": list(self.keywords),
        }


def p(
    name: str,
    location: ParamLocation,
    required: bool,
    description: str,
    example: str | int | bool | None = None,
) -> ParamDoc:
    return ParamDoc(name, location, required, description, example)


DATE = "Date in YYYY-MM-DD format."
START = "Start date in YYYY-MM-DD format."
END = "End date in YYYY-MM-DD format."
X_API_KEY = "Requires GARMIN_API_KEY / X-API-Key for the target Garmin account."
X_ADMIN_KEY = "Requires GARMIN_API_ADMIN_KEY / X-Admin-Key."


ROUTES: tuple[RouteDoc, ...] = (
    RouteDoc(
        id="system.health",
        method="GET",
        path="/health",
        category="system",
        auth="none",
        summary="Check whether the Garmin HTTP API is alive.",
        returns='{"status": "ok"} when the API process is running.',
        response_contract="JSON object: {status: string}.",
        example="GET /health",
        keywords=("health", "status", "up", "alive", "ping"),
    ),
    RouteDoc(
        id="accounts.register",
        method="POST",
        path="/accounts",
        category="accounts",
        auth="admin",
        summary="Register a Garmin account and create an account API key.",
        returns=(
            "account_id, api_key, mfa_required and message. Store api_key "
            "because only its hash is saved."
        ),
        params=(
            p("email", "body", True, "Garmin Connect email.", "person@example.com"),
            p("password", "body", True, "Garmin Connect password."),
            p("label", "body", False, "Internal label.", "Samuel"),
            p("is_cn", "body", False, "Use Garmin China login flow.", False),
        ),
        response_contract=(
            "JSON object: {account_id: string, api_key: string, "
            "mfa_required: boolean, message: string}. "
            f"{X_ADMIN_KEY}"
        ),
        example="POST /accounts with JSON body email/password/label/is_cn.",
        keywords=("register", "create account", "login", "garmin credentials"),
    ),
    RouteDoc(
        id="accounts.mfa",
        method="POST",
        path="/accounts/mfa",
        category="accounts",
        auth="account",
        summary="Complete a pending Garmin MFA login.",
        returns="Status message after Garmin MFA is completed and tokens are saved.",
        params=(p("mfa_code", "body", True, "Garmin one-time MFA code.", "123456"),),
        response_contract='JSON object: {status: "ok", message: string}.',
        example="POST /accounts/mfa with JSON body {mfa_code: '123456'}.",
        keywords=("mfa", "2fa", "code", "authentication", "login"),
    ),
    RouteDoc(
        id="accounts.me",
        method="GET",
        path="/me",
        category="accounts",
        auth="account",
        summary="Validate the account API key and Garmin login state.",
        returns="account_id, optional label and authenticated=true when login works.",
        response_contract=(
            "JSON object: {account_id: string, label: string|null, "
            "authenticated: boolean}. "
            f"{X_API_KEY}"
        ),
        example="GET /me",
        keywords=("me", "account", "authenticated", "token", "login"),
    ),
    RouteDoc(
        id="accounts.devices",
        method="GET",
        path="/devices",
        category="accounts",
        auth="account",
        summary="List Garmin devices registered to the account.",
        returns="Garmin raw list of registered devices.",
        example="GET /devices",
        keywords=("devices", "watch", "garmin device", "forerunner", "fenix"),
    ),
    RouteDoc(
        id="daily_report.get",
        method="GET",
        path="/daily-report/{date}",
        category="daily_report",
        auth="account",
        summary="Get one aggregated daily report for personal Garmin data.",
        returns=(
            "summary, health, training, body, nutrition and warnings. Missing "
            "Garmin sections are null and listed in warnings."
        ),
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        response_contract=(
            "JSON object: {account_id, date, cached, summary, health, training, "
            "body, nutrition, warnings}. Optimized entry point for questions "
            "about a specific day."
        ),
        example="GET /daily-report/2026-05-26",
        keywords=(
            "daily report",
            "today",
            "ontem",
            "relatorio diario",
            "all metrics",
            "summary",
        ),
    ),
    RouteDoc(
        id="health.summary",
        method="GET",
        path="/summary/{date}",
        category="health",
        auth="account",
        summary="Get Garmin daily summary.",
        returns=(
            "Calories, active calories, consumed calories, remaining calories, "
            "steps, distance and daily totals when Garmin provides them."
        ),
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /summary/2026-05-26",
        keywords=("summary", "calories", "steps", "distance", "calorias", "passos"),
    ),
    RouteDoc(
        id="health.stats",
        method="GET",
        path="/stats/{date}",
        category="health",
        auth="account",
        summary="Compatibility alias for daily summary.",
        returns="Same Garmin payload as /summary/{date}.",
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /stats/2026-05-26",
        keywords=("stats", "statistics", "summary", "daily"),
    ),
    RouteDoc(
        id="body.stats_and_body",
        method="GET",
        path="/stats-and-body/{date}",
        category="body",
        auth="account",
        summary="Get daily stats merged with body-composition averages.",
        returns="Daily summary fields merged with body-composition averages.",
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /stats-and-body/2026-05-26",
        keywords=("body", "composition", "weight", "peso", "stats"),
    ),
    RouteDoc(
        id="health.heart_rate",
        method="GET",
        path="/heart-rate/{date}",
        category="health",
        auth="account",
        summary="Get daily heart-rate timeline.",
        returns="Resting heart rate, min/max and intraday samples when available.",
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /heart-rate/2026-05-26",
        keywords=("heart rate", "batimentos", "bpm", "resting", "cardiaco"),
    ),
    RouteDoc(
        id="health.sleep",
        method="GET",
        path="/sleep/{date}",
        category="health",
        auth="account",
        summary="Get Garmin sleep data.",
        returns="Sleep summary, sleep stages and sleep measurements.",
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /sleep/2026-05-26",
        keywords=("sleep", "sono", "dormi", "stages", "deep sleep", "rem"),
    ),
    RouteDoc(
        id="health.hrv",
        method="GET",
        path="/hrv/{date}",
        category="health",
        auth="account",
        summary="Get heart-rate variability data.",
        returns="HRV summary and timeline values when available.",
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /hrv/2026-05-26",
        keywords=("hrv", "variability", "vfc", "variabilidade"),
    ),
    RouteDoc(
        id="health.stress",
        method="GET",
        path="/stress/{date}",
        category="health",
        auth="account",
        summary="Get Garmin daily stress data.",
        returns="Stress summary and timeline values.",
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /stress/2026-05-26",
        keywords=("stress", "estresse", "stress level"),
    ),
    RouteDoc(
        id="health.resting_heart_rate",
        method="GET",
        path="/resting-heart-rate/{date}",
        category="health",
        auth="account",
        summary="Get resting heart-rate metric.",
        returns="Resting heart-rate data for the requested day.",
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /resting-heart-rate/2026-05-26",
        keywords=("resting heart rate", "rhr", "bpm repouso", "pulso"),
    ),
    RouteDoc(
        id="health.respiration",
        method="GET",
        path="/respiration/{date}",
        category="health",
        auth="account",
        summary="Get respiration data.",
        returns="Respiration measurements for the requested day.",
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /respiration/2026-05-26",
        keywords=("respiration", "breathing", "respiracao"),
    ),
    RouteDoc(
        id="health.spo2",
        method="GET",
        path="/spo2/{date}",
        category="health",
        auth="account",
        summary="Get blood oxygen saturation data.",
        returns="SpO2 measurements for the requested day.",
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /spo2/2026-05-26",
        keywords=("spo2", "oxygen", "oxigenio", "saturation"),
    ),
    RouteDoc(
        id="health.hydration",
        method="GET",
        path="/hydration/{date}",
        category="health",
        auth="account",
        summary="Get hydration data.",
        returns="Garmin hydration totals and goals when available.",
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /hydration/2026-05-26",
        keywords=("hydration", "water", "agua", "hidratacao"),
    ),
    RouteDoc(
        id="health.intensity_minutes",
        method="GET",
        path="/intensity-minutes/{date}",
        category="health",
        auth="account",
        summary="Get intensity minutes.",
        returns="Moderate/vigorous intensity minutes and goals.",
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /intensity-minutes/2026-05-26",
        keywords=("intensity", "active minutes", "minutos intensos", "atividade"),
    ),
    RouteDoc(
        id="health.steps",
        method="GET",
        path="/steps/{date}",
        category="health",
        auth="account",
        summary="Get intraday step chart.",
        returns="Step samples throughout the requested day.",
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /steps/2026-05-26",
        keywords=("steps", "passos", "walking", "walk"),
    ),
    RouteDoc(
        id="health.daily_steps",
        method="GET",
        path="/daily-steps",
        category="health",
        auth="account",
        summary="Get daily step totals for a date range.",
        returns="Daily step totals between start and end.",
        params=(
            p("start", "query", True, START, "2026-05-01"),
            p("end", "query", True, END, "2026-05-26"),
        ),
        example="GET /daily-steps?start=2026-05-01&end=2026-05-26",
        keywords=("steps range", "passos periodo", "daily steps"),
    ),
    RouteDoc(
        id="health.floors",
        method="GET",
        path="/floors/{date}",
        category="health",
        auth="account",
        summary="Get floors climbed.",
        returns="Floors climbed chart data.",
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /floors/2026-05-26",
        keywords=("floors", "stairs", "andares", "escadas"),
    ),
    RouteDoc(
        id="training.readiness",
        method="GET",
        path="/training-readiness/{date}",
        category="training",
        auth="account",
        summary="Get Garmin training readiness.",
        returns="Training readiness score and supporting context.",
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /training-readiness/2026-05-26",
        keywords=("training readiness", "prontidao", "treino", "recovery"),
    ),
    RouteDoc(
        id="training.status",
        method="GET",
        path="/training-status/{date}",
        category="training",
        auth="account",
        summary="Get aggregated training status.",
        returns="Garmin training status for the requested date.",
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /training-status/2026-05-26",
        keywords=("training status", "productive", "treino", "status"),
    ),
    RouteDoc(
        id="training.max_metrics",
        method="GET",
        path="/max-metrics/{date}",
        category="training",
        auth="account",
        summary="Get max performance metrics.",
        returns="Performance max metrics such as VO2 data when available.",
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /max-metrics/2026-05-26",
        keywords=("vo2", "max metrics", "performance", "desempenho"),
    ),
    RouteDoc(
        id="training.fitness_age",
        method="GET",
        path="/fitness-age/{date}",
        category="training",
        auth="account",
        summary="Get fitness age.",
        returns="Garmin fitness-age data.",
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /fitness-age/2026-05-26",
        keywords=("fitness age", "idade fitness", "fitness"),
    ),
    RouteDoc(
        id="body.body_battery",
        method="GET",
        path="/body-battery",
        category="body",
        auth="account",
        summary="Get body battery values for a date or range.",
        returns="Body battery reports from start through optional end.",
        params=(
            p("start", "query", True, START, "2026-05-26"),
            p("end", "query", False, END, "2026-05-26"),
        ),
        example="GET /body-battery?start=2026-05-26",
        keywords=("body battery", "energia", "bateria corporal", "recovery"),
    ),
    RouteDoc(
        id="body.body_battery_events",
        method="GET",
        path="/body-battery/events/{date}",
        category="body",
        auth="account",
        summary="Get body battery events.",
        returns="Events affecting body battery such as sleep, activities and naps.",
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /body-battery/events/2026-05-26",
        keywords=("body battery events", "nap", "activity event", "energia"),
    ),
    RouteDoc(
        id="body.body_composition",
        method="GET",
        path="/body-composition",
        category="body",
        auth="account",
        summary="Get body composition for a date or range.",
        returns="Weight and body-composition data between start and optional end.",
        params=(
            p("start", "query", True, START, "2026-05-26"),
            p("end", "query", False, END, "2026-05-26"),
        ),
        example="GET /body-composition?start=2026-05-26",
        keywords=("body composition", "peso", "weight", "fat", "muscle"),
    ),
    RouteDoc(
        id="body.weigh_ins",
        method="GET",
        path="/weigh-ins",
        category="body",
        auth="account",
        summary="Get weigh-ins for a date range.",
        returns="Garmin weigh-ins between start and end.",
        params=(
            p("start", "query", True, START, "2026-05-01"),
            p("end", "query", True, END, "2026-05-26"),
        ),
        example="GET /weigh-ins?start=2026-05-01&end=2026-05-26",
        keywords=("weigh-ins", "peso", "weight range", "balanca"),
    ),
    RouteDoc(
        id="body.daily_weigh_ins",
        method="GET",
        path="/weigh-ins/{date}",
        category="body",
        auth="account",
        summary="Get weigh-ins for a single day.",
        returns="Garmin weigh-ins for the requested day.",
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /weigh-ins/2026-05-26",
        keywords=("daily weigh-in", "daily weight", "weight"),
    ),
    RouteDoc(
        id="body.blood_pressure",
        method="GET",
        path="/blood-pressure",
        category="body",
        auth="account",
        summary="Get blood-pressure measurements.",
        returns="Blood-pressure measurements between start and optional end.",
        params=(
            p("start", "query", True, START, "2026-05-26"),
            p("end", "query", False, END, "2026-05-26"),
        ),
        example="GET /blood-pressure?start=2026-05-26",
        keywords=("blood pressure", "pressao", "systolic", "diastolic"),
    ),
    RouteDoc(
        id="nutrition.food_log",
        method="GET",
        path="/nutrition/food-log/{date}",
        category="nutrition",
        auth="account",
        summary="Get Garmin Connect+ daily food log.",
        returns="Food log, consumed calories, macros and logged food summaries.",
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /nutrition/food-log/2026-05-26",
        keywords=("nutrition", "food", "calories", "macros", "alimentacao", "comida"),
    ),
    RouteDoc(
        id="nutrition.meals",
        method="GET",
        path="/nutrition/meals/{date}",
        category="nutrition",
        auth="account",
        summary="Get Garmin Connect+ meal entries.",
        returns="Meal entries for breakfast, lunch, dinner or snacks when available.",
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /nutrition/meals/2026-05-26",
        keywords=("meals", "refeicoes", "breakfast", "lunch", "dinner", "snack"),
    ),
    RouteDoc(
        id="nutrition.settings",
        method="GET",
        path="/nutrition/settings/{date}",
        category="nutrition",
        auth="account",
        summary="Get Garmin Connect+ nutrition targets/settings.",
        returns="Calorie and macronutrient goals/settings when Garmin provides them.",
        params=(p("date", "path", True, DATE, "2026-05-26"),),
        example="GET /nutrition/settings/2026-05-26",
        keywords=("nutrition settings", "macro targets", "calorie goal", "metas"),
    ),
    RouteDoc(
        id="nutrition.food_photo_analyze",
        method="POST",
        path="/nutrition/food-photo/analyze",
        category="nutrition",
        auth="account",
        summary="Experimental food-photo analysis contract.",
        returns=(
            "HTTP 501 placeholder until a Garmin photo upload endpoint is mapped. "
            "Validates image uploads and returns implementation next steps."
        ),
        params=(
            p("photo", "form", True, "Food image file path for MCP clients."),
            p("meal_type", "form", False, "breakfast, lunch, dinner or snack.", "lunch"),
            p("notes", "form", False, "Portion/context notes.", "rice and chicken"),
        ),
        response_contract=(
            "HTTP 501 JSON object: {account_id, status, message, "
            "garmin_connect_plus_feature, filename, content_type, meal_type, "
            "notes, next_steps}."
        ),
        example="POST multipart /nutrition/food-photo/analyze with photo=@meal.jpg.",
        keywords=("photo food", "image", "calories", "ai", "camera", "comida foto"),
    ),
    RouteDoc(
        id="training.activities",
        method="GET",
        path="/activities",
        category="training",
        auth="account",
        summary="List recent Garmin activities.",
        returns="Paginated activity summaries.",
        params=(
            p("start", "query", False, "Pagination offset.", 0),
            p("limit", "query", False, "Page size, 1 to 100.", 20),
            p("activity_type", "query", False, "Garmin activity type filter.", "running"),
        ),
        example="GET /activities?start=0&limit=20&activity_type=running",
        keywords=("activities", "runs", "cycling", "workouts", "corrida", "treinos"),
    ),
    RouteDoc(
        id="training.activity",
        method="GET",
        path="/activities/{activity_id}",
        category="training",
        auth="account",
        summary="Get one activity summary/detail payload.",
        returns="Garmin summary/details for a single activity id.",
        params=(p("activity_id", "path", True, "Garmin activity id.", "123456789"),),
        example="GET /activities/123456789",
        keywords=("activity detail", "run detail", "activity id", "treino"),
    ),
    RouteDoc(
        id="training.activity_details",
        method="GET",
        path="/activities/{activity_id}/details",
        category="training",
        auth="account",
        summary="Get detailed activity chart/polyline data.",
        returns="Detailed chart samples and polyline data.",
        params=(
            p("activity_id", "path", True, "Garmin activity id.", "123456789"),
            p("maxchart", "query", False, "Maximum chart samples.", 2000),
            p("maxpoly", "query", False, "Maximum polyline points.", 4000),
        ),
        example="GET /activities/123456789/details?maxchart=2000&maxpoly=4000",
        keywords=("activity charts", "polyline", "pace", "heart rate", "gps"),
    ),
    RouteDoc(
        id="training.activity_download",
        method="GET",
        path="/activities/{activity_id}/download",
        category="training",
        auth="account",
        summary="Download an activity file.",
        returns="Raw activity file content in original, TCX, GPX, KML or CSV format.",
        params=(
            p("activity_id", "path", True, "Garmin activity id.", "123456789"),
            p("fmt", "query", False, "original, tcx, gpx, kml or csv.", "tcx"),
        ),
        response_contract=(
            "File response. The MCP wrapper returns content_type, byte length and "
            "a text preview when possible to avoid sending large binaries to the LLM."
        ),
        example="GET /activities/123456789/download?fmt=tcx",
        keywords=("download", "tcx", "gpx", "fit", "csv", "activity file"),
    ),
)

ROUTES_BY_ID: dict[str, RouteDoc] = {route.id: route for route in ROUTES}
CATEGORIES: tuple[str, ...] = tuple(sorted({route.category for route in ROUTES}))
