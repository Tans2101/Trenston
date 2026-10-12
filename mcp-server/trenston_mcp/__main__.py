"""Run the Trenston MCP server.

    python -m trenston_mcp                 # stdio, key from TRENSTON_API_KEY
    python -m trenston_mcp --http          # streamable HTTP on $PORT (default 8000), key per request
"""
from __future__ import annotations

import argparse
import os

from mcp.server.transport_security import TransportSecuritySettings

from trenston_mcp.server import build_server


def _allowed_hosts(port: int) -> list[str]:
    raw = os.environ.get("MCP_ALLOWED_HOSTS", "")
    hosts = [h.strip() for h in raw.split(",") if h.strip()]
    return hosts or ["localhost", "127.0.0.1", f"localhost:{port}", f"127.0.0.1:{port}"]


def main() -> None:
    parser = argparse.ArgumentParser(prog="trenston_mcp", description="Trenston MCP server (read-only)")
    parser.add_argument("--http", action="store_true", help="Serve streamable HTTP instead of stdio")
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()

    if not args.http:
        build_server(http_mode=False).run("stdio")
        return

    server = build_server(http_mode=True)
    server.run(
        "streamable-http",
        host=args.host,
        port=args.port,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        # Host header allow-list (DNS rebinding protection). Set MCP_ALLOWED_HOSTS to the
        # public hostname in production, e.g. "mcp.trenston.com".
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=_allowed_hosts(args.port),
            allowed_origins=[],
        ),
    )


if __name__ == "__main__":
    main()
