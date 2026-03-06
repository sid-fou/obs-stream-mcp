"""Cluster manager for distributed obs-stream-mcp coordination.

Loads cluster configuration, manages remote MCP client instances,
and provides tool implementations for cluster operations.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from obs_stream_mcp.coordination.remote_mcp_client import RemoteMCPClient
from obs_stream_mcp.errors import (
    ErrorCode,
    error_response,
    success_response,
)


class ClusterManager:
    """Manages connections to remote obs-stream-mcp nodes."""

    def __init__(self, config_path: str | None = None) -> None:
        self._nodes: dict[str, RemoteMCPClient] = {}
        self._token = os.environ.get("CLUSTER_AUTH_TOKEN", "")
        self._config_path = config_path
        self._load_config()

    def _load_config(self) -> None:
        """Load cluster configuration from file or environment."""
        # Try explicit path, then env var, then default locations.
        paths_to_try = []
        if self._config_path:
            paths_to_try.append(Path(self._config_path))
        env_path = os.environ.get("CLUSTER_CONFIG_PATH")
        if env_path:
            paths_to_try.append(Path(env_path))
        # Default: look next to the project root.
        paths_to_try.append(Path(__file__).resolve().parent.parent.parent.parent / "cluster_config.json")

        for path in paths_to_try:
            if path.is_file():
                try:
                    with open(path) as f:
                        config = json.load(f)
                    self._apply_config(config)
                    return
                except (json.JSONDecodeError, KeyError) as exc:
                    # Bad config — continue to next candidate.
                    continue

        # No config found — cluster is empty (local-only mode).
        self._nodes = {}

    def _apply_config(self, config: dict[str, Any]) -> None:
        """Apply a parsed cluster config dict."""
        nodes = config.get("cluster_nodes", [])
        for node in nodes:
            name = node.get("name", "")
            host = node.get("host", "")
            port = node.get("port", 8765)
            if name and host:
                self._nodes[name] = RemoteMCPClient(
                    name=name,
                    host=host,
                    port=port,
                    token=self._token,
                )

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def cluster_nodes_list(self) -> dict[str, Any]:
        """List all configured cluster nodes."""
        nodes = []
        for name, client in self._nodes.items():
            nodes.append({
                "name": name,
                "host": client.host,
                "port": client.port,
            })
        return success_response({
            "nodes": nodes,
            "node_count": len(nodes),
        })

    async def cluster_status(self) -> dict[str, Any]:
        """Check reachability of all cluster nodes."""
        statuses = {}
        for name, client in self._nodes.items():
            result = await client.ping()
            if result["success"]:
                statuses[name] = "online"
            else:
                statuses[name] = "offline"
        return success_response({
            "nodes": statuses,
            "online_count": sum(1 for s in statuses.values() if s == "online"),
            "total_count": len(statuses),
        })

    async def cluster_node_status(self, node_name: str) -> dict[str, Any]:
        """Detailed status of a specific cluster node.

        Verifies: MCP reachable, OBS reachable on that node, tool discovery.
        """
        client = self._nodes.get(node_name)
        if client is None:
            return error_response(
                ErrorCode.NODE_NOT_FOUND,
                f"Node '{node_name}' not found in cluster config. "
                f"Available: {sorted(self._nodes.keys())}",
            )

        status = {
            "node": node_name,
            "host": client.host,
            "port": client.port,
            "mcp_reachable": False,
            "obs_reachable": False,
            "tool_count": 0,
            "tools": [],
        }

        # 1. Check MCP reachability.
        ping_result = await client.ping()
        if not ping_result["success"]:
            status["error"] = ping_result.get("error", "unreachable")
            return success_response(status)
        status["mcp_reachable"] = True

        # 2. Discover tools.
        tools_result = await client.list_tools()
        if tools_result["success"]:
            status["tool_count"] = tools_result["data"]["tool_count"]
            status["tools"] = [t["name"] for t in tools_result["data"]["tools"]]

        # 3. Check OBS connectivity by calling obs_get_status remotely.
        obs_result = await client.call_tool("obs_get_status")
        if obs_result.get("success"):
            status["obs_reachable"] = True
            status["obs_status"] = obs_result.get("data", {})
        else:
            status["obs_error"] = obs_result.get("error", "unknown")

        return success_response(status)

    async def remote_execute(
        self, node_name: str, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Forward a tool call to a remote node.

        Only allows execution of existing MCP tools — no arbitrary commands.
        """
        client = self._nodes.get(node_name)
        if client is None:
            return error_response(
                ErrorCode.NODE_NOT_FOUND,
                f"Node '{node_name}' not found in cluster config. "
                f"Available: {sorted(self._nodes.keys())}",
            )

        return await client.call_tool(tool_name, arguments)
