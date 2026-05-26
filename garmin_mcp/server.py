"""Model Context Protocol server for the private Garmin HTTP API."""

from __future__ import annotations

import os
from datetime import date as date_type
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import DEFAULT_MAX_CHARS, GarminApiClient, env_int
from .rag import index_markdown, route_markdown, search_routes
from .routes import CATEGORIES, ROUTES, ROUTES_BY_ID

MCP_INSTRUCTIONS = """
Use this server to answer questions about a user's Garmin data with minimal
context. First search route contracts with search_garmin_docs or use
build_garmin_context. Then call the smallest Garmin route that answers the
question. Prefer daily-report only when the user asks broad daily questions.
Never ask the user for Garmin credentials in chat; this server reads
GARMIN_API_BASE_URL, GARMIN_API_KEY and optional GARMIN_API_ADMIN_KEY from env.
""".strip()

mcp = FastMCP("Garmin Connect MCP", instructions=MCP_INSTRUCTIONS)


def today_iso() -> str:
    return date_type.today().isoformat()


def client() -> GarminApiClient:
    return GarminApiClient.from_env()


def default_max_chars() -> int:
    return env_int("GARMIN_MCP_MAX_RESPONSE_CHARS", DEFAULT_MAX_CHARS)


@mcp.resource("garmin://docs/routes")
def docs_routes() -> str:
    """Compact markdown index of all Garmin API route contracts."""
    return index_markdown()


@mcp.resource("garmin://docs/categories")
def docs_categories() -> str:
    """Available route categories for filtering RAG searches."""
    return "\n".join(f"- {category}" for category in CATEGORIES)


@mcp.resource("garmin://docs/route/{route_id}")
def docs_route(route_id: str) -> str:
    """Full markdown contract for one route id."""
    route = ROUTES_BY_ID.get(route_id)
    if route is None:
        valid = ", ".join(sorted(ROUTES_BY_ID))
        return f"Unknown route_id: {route_id}\n\nValid route ids: {valid}"
    return route_markdown(route)


@mcp.tool()
def list_garmin_routes(category: str | None = None) -> dict[str, Any]:
    """List compact route contracts, optionally filtered by category."""
    if category and category not in CATEGORIES:
        return {"error": f"Unknown category '{category}'", "categories": CATEGORIES}
    routes = [
        route.compact()
        for route in ROUTES
        if not category or route.category == category
    ]
    return {"count": len(routes), "routes": routes}


@mcp.tool()
def search_garmin_docs(
    query: str,
    limit: int = 5,
    category: str | None = None,
) -> dict[str, Any]:
    """Search Garmin API route contracts with local RAG/BM25-style retrieval."""
    return {
        "query": query,
        "category": category,
        "results": search_routes(query, limit=limit, category=category),
    }


@mcp.tool()
def get_route_contract(route_id: str) -> dict[str, Any]:
    """Return the complete contract for one Garmin route id."""
    route = ROUTES_BY_ID.get(route_id)
    if route is None:
        return {
            "error": f"Unknown route_id '{route_id}'",
            "valid_route_ids": sorted(ROUTES_BY_ID),
        }
    return route.full_contract()


@mcp.tool()
def call_garmin_route(
    route_id: str,
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
    max_chars: int | None = None,
    raw: bool = False,
) -> dict[str, Any]:
    """Call any documented Garmin API route by route_id.

    Use get_route_contract first if unsure which parameters are required.
    Responses are compacted by default to reduce LLM token usage.
    """
    return client().request_route(
        route_id,
        date=date,
        start=start,
        end=end,
        activity_id=activity_id,
        fmt=fmt,
        activity_type=activity_type,
        limit=limit,
        offset=offset,
        maxchart=maxchart,
        maxpoly=maxpoly,
        body=body,
        photo_path=photo_path,
        max_chars=max_chars or default_max_chars(),
        raw=raw,
    )


@mcp.tool()
def get_daily_report(
    date: str | None = None,
    max_chars: int | None = None,
    raw: bool = False,
) -> dict[str, Any]:
    """Fetch the aggregated Garmin daily report for a date.

    If date is omitted, the server's current date is used.
    """
    return call_garmin_route(
        "daily_report.get",
        date=date or today_iso(),
        max_chars=max_chars,
        raw=raw,
    )


@mcp.tool()
def build_garmin_context(
    question: str,
    date: str | None = None,
    start: str | None = None,
    end: str | None = None,
    max_routes: int = 4,
    include_data: bool = True,
    max_chars_per_call: int | None = None,
) -> dict[str, Any]:
    """Build a compact context pack for a Garmin question.

    This is the token-optimized RAG path: it retrieves only relevant route
    contracts, then optionally calls safe GET routes when the needed parameters
    are available. The client LLM can answer using this compact pack.
    """
    effective_date = date or today_iso()
    docs = search_routes(question, limit=max_routes)
    data: list[dict[str, Any]] = []
    if include_data:
        for doc in docs:
            route_id = str(doc["id"])
            route = ROUTES_BY_ID[route_id]
            if route.method != "GET" or route.auth != "account":
                continue
            if "{activity_id}" in route.path:
                continue
            needs_start = any(param.name == "start" for param in route.params)
            needs_required_end = any(
                param.name == "end" and param.required for param in route.params
            )
            try:
                data.append(
                    client().request_route(
                        route_id,
                        date=effective_date if "{date}" in route.path else None,
                        start=(start or effective_date) if needs_start else None,
                        end=(end or effective_date) if needs_required_end else end,
                        max_chars=max_chars_per_call or default_max_chars(),
                    )
                )
            except Exception as exc:  # noqa: BLE001 - returned as MCP data
                data.append({"route_id": route_id, "error": str(exc)})
    return {
        "question": question,
        "date_used": effective_date,
        "retrieved_route_contracts": docs,
        "data": data,
        "token_strategy": (
            "Only the top route contracts and compacted route payloads are returned. "
            "Call get_route_contract or call_garmin_route with raw=true only when "
            "the client LLM needs more detail."
        ),
    }


@mcp.prompt()
def answer_garmin_question(question: str, date: str | None = None) -> str:
    """Prompt template for clients that want an analysis flow."""
    chosen_date = date or "today"
    return f"""
Answer this Garmin question: {question}

Use the Garmin MCP server in this order:
1. Call build_garmin_context(question={question!r}, date={chosen_date!r}).
2. If the context is insufficient, call search_garmin_docs with narrower terms.
3. Call call_garmin_route only for the smallest extra endpoint needed.
4. Explain uncertainty when Garmin returns null, truncated data, or warnings.
5. Do not expose GARMIN_API_KEY, GARMIN_API_ADMIN_KEY, Garmin password or raw secrets.
""".strip()


def main() -> None:
    transport = os.getenv("GARMIN_MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
