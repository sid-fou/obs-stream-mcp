"""MCP server entrypoint for obs-stream-mcp.

Supports two transport modes:
  - stdio (default): For Claude Desktop local integration.
    Also starts SSE in a background thread so this node is reachable
    by other cluster nodes.
  - sse: HTTP/SSE endpoint only (for headless remote nodes).

Usage:
  obs-stream-mcp                        # stdio + background SSE
  obs-stream-mcp --no-sse               # stdio only, no remote access
  obs-stream-mcp --mode sse             # SSE only on port 8765
  obs-stream-mcp --mode sse --port 9000
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
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

# Cluster coordination is optional.
try:
    from obs_stream_mcp.coordination.cluster_manager import ClusterManager
    _CLUSTER_AVAILABLE = True
except ImportError:
    _CLUSTER_AVAILABLE = False


def create_server(*, include_cluster: bool = False) -> tuple[Server, OBSController]:
    """Create and configure the MCP server and OBS controller.

    Args:
        include_cluster: If True, register cluster coordination tools
            AND auto-register prefixed remote-node tools.
    """
    server = Server("obs-stream-mcp")
    controller = OBSController()

    ui_lock = threading.Lock()
    ui_controller = None

    if _UI_AVAILABLE:
        ui_controller = OBSUIController(ui_lock=ui_lock)

    cluster_manager = None
    if include_cluster and _CLUSTER_AVAILABLE:
        cluster_manager = ClusterManager()

    register_tools(
        server, controller,
        ui_controller=ui_controller,
        cluster_manager=cluster_manager,
    )
    return server, controller


# ------------------------------------------------------------------
# SSE transport (for remote cluster access)
# ------------------------------------------------------------------

def _build_sse_app(host: str = "0.0.0.0", port: int = 8765):
    """Build the Starlette ASGI app for SSE transport.

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

    expected_token = os.environ.get("CLUSTER_AUTH_TOKEN", "")

    class AuthMiddleware(BaseHTTPMiddleware):
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

    return Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse_transport.handle_post_message),
        ],
        middleware=middleware,
    )


def _run_sse_in_thread(host: str, port: int) -> None:
    """Run the SSE server in a background thread with its own event loop.

    Uses a completely independent Server + OBSController instance so there
    are no shared-state issues with the stdio server in the main thread.
    """
    import uvicorn

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = _build_sse_app(host=host, port=port)

    # Log to stderr so it doesn't interfere with stdio MCP transport.
    print(
        f"[obs-stream-mcp] Background SSE server on {host}:{port}",
        file=sys.stderr,
    )

    config = uvicorn.Config(
        app, host=host, port=port,
        log_level="warning",  # Quiet — avoid noise on stdio.
    )
    uv_server = uvicorn.Server(config)
    loop.run_until_complete(uv_server.serve())


# ------------------------------------------------------------------
# stdio transport (default — for Claude Desktop)
# ------------------------------------------------------------------

async def run_stdio(*, sse_host: str = "0.0.0.0", sse_port: int = 8765, enable_sse: bool = True) -> None:
    """Run the MCP server over stdio.

    By default also starts an SSE server in a daemon thread so this
    node is reachable by other cluster nodes for bidirectional control.
    """
    server, _controller = create_server(include_cluster=True)

    if enable_sse:
        sse_thread = threading.Thread(
            target=_run_sse_in_thread,
            args=(sse_host, sse_port),
            daemon=True,
        )
        sse_thread.start()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


# ------------------------------------------------------------------
# SSE-only transport (for headless remote nodes)
# ------------------------------------------------------------------

async def run_sse(host: str = "0.0.0.0", port: int = 8765) -> None:
    """Run the MCP server as an HTTP/SSE endpoint only."""
    import uvicorn

    expected_token = os.environ.get("CLUSTER_AUTH_TOKEN", "")
    app = _build_sse_app(host=host, port=port)

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
        help="Transport mode: stdio (Claude Desktop) or sse (remote node)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="SSE server bind address (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("SSE_PORT", "8765")),
        help="SSE server port (default: 8765 or SSE_PORT env var)",
    )
    parser.add_argument(
        "--no-sse",
        action="store_true",
        help="Disable background SSE server in stdio mode",
    )
    args = parser.parse_args()

    if args.mode == "sse":
        asyncio.run(run_sse(host=args.host, port=args.port))
    else:
        asyncio.run(run_stdio(
            sse_host=args.host,
            sse_port=args.port,
            enable_sse=not args.no_sse,
        ))


if __name__ == "__main__":
    main()
