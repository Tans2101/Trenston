# Trenston MCP server

Read-only bridge that lets AI assistants that support the Model Context Protocol
(MCP) read a company's Trenston workspace.

It holds no data and no permissions of its own. Each tool call is forwarded to
Trenston's public API (`/api/v1`) with the caller's personal API key, and
Trenston applies the same rules as the app: people only see their own
departments, and financial data needs Financials access. API keys are available
on the Growth and Business plans.

## Tools

| Tool | What it returns |
|---|---|
| `get_me` | Workspace, person, and whether they can see financials |
| `get_briefing` | Headline, metrics, what changed, what to decide, what to delegate, team updates |
| `list_decisions` | Open decisions with recommendation and confidence, plus drafted suggestions |
| `list_tasks` | Task board with status, assignee, due date, overdue flag |
| `get_my_work` | The caller's open items across departments |
| `get_financials` | MRR, ARR, burn, cash, runway, monthly totals (Financials access only) |

Every tool is marked read-only. Nothing can be changed in Trenston through this server.

## Get an API key

In Trenston: **Settings → API keys → Create key**. The key starts with `trn_`
and is shown once. Revoke it there at any time.

## Run locally (stdio)

For desktop assistants that launch MCP servers as a local command:

```bash
pip install -r requirements.txt
TRENSTON_API_KEY=trn_... python -m trenston_mcp
```

Example client config (format varies by assistant):

```json
{
  "mcpServers": {
    "trenston": {
      "command": "python",
      "args": ["-m", "trenston_mcp"],
      "cwd": "/path/to/Trenston/mcp-server",
      "env": { "TRENSTON_API_KEY": "trn_..." }
    }
  }
}
```

## Run hosted (streamable HTTP)

```bash
python -m trenston_mcp --http            # serves /mcp on $PORT (default 8000)
```

Clients send their own key with every request:
`Authorization: Bearer trn_...` (or `X-API-Key: trn_...`).
In HTTP mode the server never uses a `TRENSTON_API_KEY` environment variable,
so one person's request can never be answered with another person's key.

### Environment

| Variable | Default | Purpose |
|---|---|---|
| `TRENSTON_API_BASE` | `https://www.trenston.com/api` | Trenston API to call |
| `MCP_ALLOWED_HOSTS` | localhost only | Comma-separated Host headers to accept (DNS rebinding protection), e.g. `mcp.trenston.com` |
| `PORT` | `8000` | HTTP port |

### Render settings (new Web Service)

- Root directory: `mcp-server`
- Runtime: Python 3.12
- Build command: `pip install -r requirements.txt`
- Start command: `python -m trenston_mcp --http`
- Environment: `MCP_ALLOWED_HOSTS` set to the service's public hostname
  (for example `trenston-mcp.onrender.com`, or `mcp.trenston.com` once DNS points there)

## Sign-in note

This first version authenticates with personal API keys. Some hosted assistant
integrations expect an OAuth sign-in flow instead of a pasted key; that is not
built yet. Check each assistant's current MCP documentation before promising
support for a specific one.

## Tests

```bash
pip install -r requirements.txt pytest pytest-asyncio
PYTHONPATH=. python -m pytest -q
```
