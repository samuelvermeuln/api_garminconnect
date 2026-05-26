# Garmin MCP Server

This project includes an MCP server for connecting LLM clients to the private
Garmin HTTP API without loading the full API documentation into every prompt.

The MCP server exposes:

- Route documentation resources under `garmin://docs/...`.
- A local RAG search tool over all route contracts.
- Tools that call the Garmin HTTP API with `X-API-Key`.
- A compact context builder for natural-language questions about Garmin data.

## Install

```bash
pip install -e ".[api,mcp]"
```

The Garmin HTTP API must already be running and the target Garmin account must
already have an account API key from `POST /accounts`.

## Environment

```bash
export GARMIN_API_BASE_URL="http://167.86.116.131:8001"
export GARMIN_API_KEY="account-api-key-from-post-accounts"
```

Optional:

```bash
export GARMIN_API_ADMIN_KEY="admin-key-for-post-accounts"
export GARMIN_MCP_MAX_RESPONSE_CHARS=12000
export GARMIN_MCP_TIMEOUT_SECONDS=30
export GARMIN_MCP_TRANSPORT=stdio
```

`GARMIN_API_KEY` is the normal account API key returned by the Garmin HTTP API.
The MCP server does not ask the user for Garmin credentials in chat.

## Run

```bash
python -m garmin_mcp.server
```

Or with PDM:

```bash
pdm run mcp
```

The default transport is `stdio`, which is what most desktop MCP clients expect.

## Client Config Example

```json
{
  "mcpServers": {
    "garmin": {
      "command": "python",
      "args": ["-m", "garmin_mcp.server"],
      "env": {
        "GARMIN_API_BASE_URL": "http://167.86.116.131:8001",
        "GARMIN_API_KEY": "account-api-key-from-post-accounts"
      }
    }
  }
}
```

## Resources

- `garmin://docs/routes` - compact route index.
- `garmin://docs/categories` - route categories.
- `garmin://docs/route/{route_id}` - full contract for a single route.

## Tools

- `list_garmin_routes(category)` - compact list of known routes.
- `search_garmin_docs(query, limit, category)` - local RAG search over route
  contracts.
- `get_route_contract(route_id)` - full method/path/auth/params/response
  contract.
- `call_garmin_route(...)` - generic route caller by `route_id`.
- `get_daily_report(date)` - shortcut for `daily_report.get`.
- `build_garmin_context(question, date, start, end)` - token-optimized context
  pack for answering questions about Garmin data.

## Route IDs

The MCP server uses stable `route_id` values so the LLM does not need to carry
full paths in context. Examples:

- `daily_report.get`
- `health.sleep`
- `health.summary`
- `health.heart_rate`
- `training.activities`
- `training.readiness`
- `body.body_battery`
- `body.body_composition`
- `nutrition.food_log`
- `nutrition.meals`
- `nutrition.food_photo_analyze`

Use `list_garmin_routes` or `garmin://docs/routes` for the complete list.

## RAG Strategy

The RAG layer is intentionally local and cheap:

1. Route contracts are stored in `garmin_mcp/routes.py`.
2. `search_garmin_docs` tokenizes English and Portuguese health terms.
3. It ranks route contracts with a small BM25-style scorer.
4. `build_garmin_context` returns only the top route docs and compacted API
   payloads.
5. Large Garmin payloads are truncated by `GARMIN_MCP_MAX_RESPONSE_CHARS`.

This keeps prompts smaller than sending `/openapi.json` or a full daily report
for every user question.

## Example Questions

Ask your LLM:

- "Como foi meu sono hoje?"
- "Quantas calorias eu consumi e gastei ontem?"
- "Minha body battery explica meu cansaço?"
- "Resumo do meu treino mais recente."
- "Monte um relatorio diario do meu Garmin."

The client LLM should call `build_garmin_context` first, then request narrower
routes only when needed.

## Security Notes

- Keep `GARMIN_API_KEY` and `GARMIN_API_ADMIN_KEY` in the MCP client environment,
  not in prompts.
- Prefer HTTPS for `GARMIN_API_BASE_URL` outside localhost.
- The MCP server returns compact payloads by default to avoid sending large
  health datasets unnecessarily.
