"""MCP server entrypoint for obs-stream-mcp.

Supports two transport modes:
  - stdio (default): For Claude Desktop local integration.
  - sse: HTTP/SSE endpoint for remote MCP-to-MCP cluster access.

Usage:
  obs-stream-mcp                  # stdio mode (default)
  obs-stream-mcp --mode sse       # SSE mode on port 8765
  obs-stream-mcp --mode sse --port 9000
"""

from __future__ import annotations

import argparse
import asyncio
import os
import threading

from mcp.server import Server
from mcp.server.stdio import stdio_server

from obs_stream_mcp.obs_controller import OBSController
from obs_stream_mcp.tools import register_tools

# UI automation is optional — requires pywinauto (Windows only).
try:
    from obs_stream_mcp.obs_ui_controller import OBSUIController
    _UI_AVAILABLE = True
except ImportError:
    _UI_AVAILABLE = False

# Cluster coordination is optional — only loaded in stdio mode.
try:
    from obs_stream_mcp.coordination.cluster_manager import ClusterManager

    _CLUSTER_AVAILABLE = True
except ImportError:
    _CLUSTER_AVAILABLE = False


def create_server(*, include_cluster: bool = False) -> tuple[Server, OBSController]:
    """Create and configure the MCP server and OBS controller.

    Args:
        include_cluster: If True, register cluster coordination tools.
            Only enabled in stdio mode (the node that Claude talks to).
            SSE nodes are remotes and don't need cluster tools.
    """
    server = Server("obs-stream-mcp")
    controller = OBSController()

    # Shared lock prevents concurrent UI automation and WebSocket operations.
    ui_lock = threading.Lock()
    ui_controller = None

    if _UI_AVAILABLE:
        ui_controller = OBSUIController(ui_lock=ui_lock)

    cluster_manager = None
    if include_cluster and _CLUSTER_AVAILABLE:
        cluster_manager = ClusterManager()

    register_tools(server, controller, ui_controller=ui_controller, cluster_manager=cluster_manager)
    return server, controller


# ------------------------------------------------------------------
# stdio transport (default — for Claude Desktop)
# ------------------------------------------------------------------

async def run_stdio() -> None:
    """Run the MCP server over stdio."""
    server, _controller = create_server(include_cluster=True)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


# ------------------------------------------------------------------
# SSE transport (for remote cluster access)
# ------------------------------------------------------------------

async def run_sse(host: str = "0.0.0.0", port: int = 8765) -> None:
    """Run the MCP server as an HTTP/SSE endpoint.

    SSE nodes do NOT register cluster tools — they are remotes.
    Auth token is checked via the CLUSTER_AUTH_TOKEN env var.
    """
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route
    from mcp.server.sse import SseServerTransport
    import uvicorn

    expected_token = os.environ.get("CLUSTER_AUTH_TOKEN", "")

    class AuthMiddleware(BaseHTTPMiddleware):
        """Reject requests without a valid Bearer token (if token is set)."""

        async def dispatch(self, request: Request, call_next):
            if expected_token:
                auth_header = request.headers.get("Authorization", "")
                if auth_header != f"Bearer {expected_token}":
                    return JSONResponse(
                        {"error": "Invalid or missing auth token"},
                        status_code=401,
                    )
            return await call_next(request)

    server, _controller = create_server(include_cluster=False)
    sse_transport = SseServerTransport("/messages/")

    async def handle_sse(request: Request):
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    middleware = [Middleware(AuthMiddleware)] if expected_token else []

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse_transport.handle_post_message),
        ],
        middleware=middleware,
    )

    print(f"obs-stream-mcp SSE server starting on {host}:{port}")
    if expected_token:
        print("Auth token required for connections.")
    else:
        print("WARNING: No CLUSTER_AUTH_TOKEN set — accepting all connections.")

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    uv_server = uvicorn.Server(config)
    await uv_server.serve()


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def main() -> None:
    """CLI entrypoint with mode selection."""
    parser = argparse.ArgumentParser(description="obs-stream-mcp server")
    parser.add_argument(
        "--mode",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport mode: stdio (Claude Desktop) or sse (remote cluster node)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="SSE server bind address (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="SSE server port (default: 8765)",
    )
    args = parser.parse_args()

    if args.mode == "sse":
        asyncio.run(run_sse(host=args.host, port=args.port))
    else:
        asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
