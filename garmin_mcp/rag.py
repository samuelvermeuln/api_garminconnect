"""Small local retrieval layer for Garmin route contracts."""

from __future__ import annotations

import math
import re
from collections import Counter

from .routes import ROUTES, RouteDoc

TOKEN_RE = re.compile(r"[a-z0-9_]+")

STOPWORDS = {
    "a",
    "about",
    "as",
    "com",
    "da",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "for",
    "get",
    "how",
    "me",
    "meu",
    "minha",
    "my",
    "o",
    "os",
    "para",
    "por",
    "que",
    "the",
    "to",
    "um",
    "uma",
}

SYNONYMS = {
    "alimentacao": "nutrition food meals calories macros comida refeicoes",
    "alimentos": "nutrition food meals calories macros comida refeicoes",
    "bateria": "body battery energia recovery recuperacao",
    "batimentos": "heart rate bpm cardiac resting",
    "calorias": "calories nutrition summary food consumed remaining",
    "cardiaco": "heart rate bpm hrv resting",
    "comida": "nutrition food meals calories macros alimentacao",
    "corrida": "activities running training activity pace gps",
    "dormi": "sleep sono rem deep awake score",
    "energia": "body battery recovery stress sleep",
    "estresse": "stress body battery recovery",
    "foto": "photo food image calories ai camera nutrition",
    "hoje": "today current date",
    "hidratação": "hydration water agua",
    "hidratacao": "hydration water agua",
    "macro": "nutrition macros protein carbs fat calories",
    "macros": "nutrition protein carbs fat calories",
    "ontem": "yesterday date",
    "oxigenio": "spo2 oxygen saturation",
    "passos": "steps daily steps walking",
    "peso": "weight weigh body composition",
    "pressao": "blood pressure systolic diastolic",
    "refeicao": "meals nutrition food",
    "refeicoes": "meals nutrition food",
    "sono": "sleep rem deep awake body battery recovery",
    "treino": "training activities readiness status performance",
}


def tokenize(text: str) -> list[str]:
    expanded = text.lower()
    for word, replacement in SYNONYMS.items():
        if word in expanded:
            expanded = f"{expanded} {replacement}"
    return [
        token
        for token in TOKEN_RE.findall(expanded)
        if len(token) > 1 and token not in STOPWORDS
    ]


def route_text(route: RouteDoc) -> str:
    param_text = " ".join(
        f"{param.name} {param.description} {param.example or ''}"
        for param in route.params
    )
    return " ".join(
        [
            route.id,
            route.method,
            route.path,
            route.category,
            route.summary,
            route.returns,
            route.response_contract,
            route.example,
            " ".join(route.keywords),
            param_text,
        ]
    )


ROUTE_TOKEN_COUNTS: dict[str, Counter[str]] = {
    route.id: Counter(tokenize(route_text(route))) for route in ROUTES
}

DOCUMENT_FREQUENCY = Counter(
    token for counts in ROUTE_TOKEN_COUNTS.values() for token in counts
)


def search_routes(
    query: str,
    *,
    limit: int = 5,
    category: str | None = None,
) -> list[dict[str, object]]:
    """Return compact route docs ranked by a BM25-like local score."""
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    query_counts = Counter(query_tokens)
    total_docs = len(ROUTES)
    results: list[tuple[float, RouteDoc]] = []
    for route in ROUTES:
        if category and route.category != category:
            continue
        counts = ROUTE_TOKEN_COUNTS[route.id]
        if not counts:
            continue
        score = 0.0
        doc_len = sum(counts.values())
        for token, query_tf in query_counts.items():
            tf = counts.get(token, 0)
            if not tf:
                continue
            idf = math.log((total_docs + 1) / (DOCUMENT_FREQUENCY[token] + 0.5))
            score += query_tf * idf * (tf / (tf + 0.5 + 0.01 * doc_len))
        if route.id in query.lower() or route.path in query.lower():
            score += 3.0
        if route.category in query.lower():
            score += 0.75
        if score > 0:
            results.append((score, route))

    results.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "score": round(score, 4),
            **route.compact(),
            "example": route.example,
            "response_contract": route.response_contract,
        }
        for score, route in results[: max(1, min(limit, 20))]
    ]


def route_markdown(route: RouteDoc) -> str:
    lines = [
        f"# {route.id}",
        "",
        f"- Method: `{route.method}`",
        f"- Path: `{route.path}`",
        f"- Category: `{route.category}`",
        f"- Auth: `{route.auth}`",
        f"- Summary: {route.summary}",
        f"- Returns: {route.returns}",
        f"- Response contract: {route.response_contract}",
    ]
    if route.params:
        lines.extend(["", "## Parameters"])
        for param in route.params:
            required = "required" if param.required else "optional"
            lines.append(
                f"- `{param.name}` in `{param.location}` ({required}): "
                f"{param.description}"
            )
    if route.example:
        lines.extend(["", "## Example", f"`{route.example}`"])
    return "\n".join(lines)


def index_markdown() -> str:
    lines = ["# Garmin MCP Route Index", ""]
    for route in ROUTES:
        lines.append(
            f"- `{route.id}` `{route.method} {route.path}` "
            f"[{route.category}] - {route.summary}"
        )
    return "\n".join(lines)
