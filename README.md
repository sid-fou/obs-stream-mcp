# obs-stream-mcp

An MCP server that gives AI assistants full control over OBS Studio — scene management, source control, streaming, multi-platform broadcasting, and distributed multi-PC setups via WebSocket v5 and Windows UI automation.

[![Ko-fi](https://img.shields.io/badge/Support%20Me-Ko--fi-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/sidfps)

## Features

- **Full OBS Control** — Scenes, sources, streaming, transforms, visibility
- **Scene Orchestration** — One-command gaming/starting-soon scene builders with rollback safety
- **Multi-RTMP Broadcasting** — Simultaneous streaming to YouTube, Twitch, Kick via obs-multi-rtmp plugin
- **Distributed Multi-PC** — Control OBS across multiple machines from a single Claude Desktop instance
- **OBS Teleport** — Zero-latency video feed between PCs via the Teleport plugin, fully automated
- **Diagnostics** — Health checks, device listing, stream settings management
- **Production-Ready** — Structured JSON responses, error codes, stream key redaction, confirmation guards

## Requirements

- Python 3.11+
- OBS Studio with WebSocket v5 enabled (Settings → Tools → WebSocket Server Settings)
- Windows OS (required for UI automation features)
- Optional: [obs-multi-rtmp](https://github.com/sorayuki/obs-multi-rtmp) plugin
- Optional: [OBS Teleport](https://github.com/fzwoch/obs-teleport) plugin

## Installation

```bash
git clone https://github.com/sid-fou/obs-stream-mcp.git
cd obs-stream-mcp
pip install -e .
```

For UI automation features (multi-RTMP, Teleport):

```bash
pip install pywinauto
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OBS_HOST` | `localhost` | OBS WebSocket host |
| `OBS_PORT` | `4455` | OBS WebSocket port |
| `OBS_PASSWORD` | `""` | OBS WebSocket password |
| `OBS_STREAM_KEY` | `""` | Stream key (used by `obs_set_stream_settings`) |

### Claude Desktop Setup

Add to your Claude Desktop config (`%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "obs-stream-mcp": {
      "command": "obs-stream-mcp",
      "env": {
        "OBS_PASSWORD": "your-obs-websocket-password"
      }
    }
  }
}
```

### Multi-PC Setup (Distributed Cluster)

For controlling OBS on multiple machines, create a `cluster_config.json` in the project root on each machine:

```json
{
  "cluster_nodes": [
    {
      "name": "streaming-pc",
      "host": "192.168.1.65",
      "port": 8765
    }
  ]
}
```

Each machine's config points to the *other* machine(s). The SSE server starts automatically on port 8765 alongside the stdio MCP server.

Remote tools are auto-registered with prefixed names (e.g., `streaming_pc__obs_connect`, `streaming_pc__obs_start_stream`), giving you full bidirectional control from either machine.

## Available Tools

### Connection & Status

| Tool | Description |
|------|-------------|
| `obs_connect` | Connect to OBS WebSocket (must be called first) |
| `obs_get_status` | Get connection and streaming status |
| `obs_health_check` | Full diagnostics: connection, streaming, recording, version, latency |
| `obs_list_devices` | List available video and audio capture devices |

### Scene Management

| Tool | Description |
|------|-------------|
| `obs_get_scene_list` | List all scenes and current active scene |
| `obs_create_scene` | Create a new empty scene |
| `obs_remove_scene` | Remove a scene (requires `confirmed=true`) |
| `obs_switch_scene` | Switch the active program scene |

### Source Management

| Tool | Description |
|------|-------------|
| `obs_add_source` | Add a source to a scene (supports all OBS input types) |
| `obs_remove_source` | Remove a source from a scene |
| `obs_get_source_list` | List all sources in a scene with properties |
| `obs_set_source_transform` | Set position, scale, rotation, crop, bounds |
| `obs_set_source_visibility` | Show or hide a source |

### Streaming

| Tool | Description |
|------|-------------|
| `obs_get_stream_settings` | Get stream service config (key redacted) |
| `obs_set_stream_settings` | Configure stream service (presets: youtube, twitch, kick, or custom RTMP) |
| `obs_start_stream` | Start streaming |
| `obs_stop_stream` | Stop streaming (requires `confirmed=true`) |

### Scene Orchestration

| Tool | Description |
|------|-------------|
| `build_gaming_scene` | Build a complete gaming scene (Game Capture, Display Capture, Webcam, Title overlay) with rollback safety |
| `build_starting_soon_scene` | Build a "Starting Soon" scene (background, optional image, optional countdown, title) |

### Multi-RTMP Broadcasting (requires obs-multi-rtmp plugin)

| Tool | Description |
|------|-------------|
| `obs_detect_multi_rtmp_plugin` | Check if the plugin is installed and visible |
| `obs_list_rtmp_targets` | List all configured RTMP targets with active/inactive state |
| `obs_add_rtmp_target` | Add a new RTMP target (name, server URL, stream key) |
| `obs_modify_rtmp_target` | Modify an existing target's settings |
| `obs_remove_rtmp_target` | Remove a target (requires `confirmed=true`) |
| `obs_start_rtmp_target` | Start streaming to a specific target |
| `obs_stop_rtmp_target` | Stop a specific target |
| `obs_start_all_rtmp_targets` | Start all targets simultaneously |
| `obs_stop_all_rtmp_targets` | Stop all active targets |

### OBS Teleport (requires OBS Teleport plugin)

| Tool | Description |
|------|-------------|
| `teleport_configure_host` | Enable/configure Teleport output on the sender machine (UI automation) |
| `teleport_configure_client` | Add a Teleport source on the receiver machine and auto-select the host from the dropdown |
| `teleport_get_status` | Check Teleport output status (WebSocket, no UI needed) |
| `setup_dual_pc_teleport` | Orchestrate full dual-PC Teleport setup across cluster nodes |

### Distributed Cluster Coordination

| Tool | Description |
|------|-------------|
| `cluster_status` | Check reachability of all cluster nodes |
| `cluster_nodes_list` | List all configured nodes with host and port |
| `cluster_node_status` | Detailed status of a specific node |
| `remote_execute` | Execute any MCP tool on a remote node |

All base tools are also available with node prefixes for remote execution (e.g., `streaming_pc__obs_connect`, `streaming_pc__build_gaming_scene`).

## Architecture

```
src/obs_stream_mcp/
├── server.py              # MCP server bootstrap (stdio + background SSE)
├── tools.py               # MCP tool handlers + dispatch + auto-prefixed remote tools
├── schemas.py             # JSON schemas for all tools
├── errors.py              # ErrorCode enum + structured response builders
├── obs_controller.py      # OBS WebSocket v5 controller
├── obs_ui_controller.py   # UI automation (obs-multi-rtmp + Teleport plugins)
├── orchestrator.py        # High-level scene builders
├── layout_loader.py       # Layout preset loader
├── layouts/default.json   # Transform presets for scene types
└── coordination/
    ├── cluster_manager.py     # Cluster config + tool implementations
    └── remote_mcp_client.py   # MCP-to-MCP SSE client
```

## Response Format

All tools return structured JSON:

```json
// Success
{"success": true, "data": {"scene_name": "Gaming", "sources": [...]}}

// Error
{"success": false, "error": "Scene not found", "code": "SCENE_NOT_FOUND"}
```

## Error Codes

| Code | Description |
|------|-------------|
| `OBS_NOT_CONNECTED` | No active OBS connection |
| `SCENE_NOT_FOUND` | Referenced scene does not exist |
| `SOURCE_NOT_FOUND` | Referenced source does not exist |
| `DUPLICATE_SCENE` | Scene with that name already exists |
| `DUPLICATE_SOURCE` | Source with that name already exists |
| `INVALID_SOURCE_TYPE` | Unknown OBS input kind |
| `STREAM_ALREADY_ACTIVE` | Stream is already running |
| `STREAM_NOT_ACTIVE` | Stream is not running |
| `STREAM_GUARD` | Cannot modify scene while streaming (use `force=true`) |
| `CONFIRMATION_REQUIRED` | Destructive action needs `confirmed=true` |
| `CONNECTION_FAILED` | Could not connect to OBS WebSocket |
| `INVALID_PARAMETER` | Invalid input parameter |
| `MULTI_RTMP_PLUGIN_NOT_FOUND` | obs-multi-rtmp plugin not detected |
| `UI_ELEMENT_NOT_FOUND` | UI automation could not find expected element |
| `UI_AUTOMATION_FAILED` | UI automation operation failed |
| `NODE_UNREACHABLE` | Remote cluster node is offline |
| `REMOTE_TOOL_NOT_FOUND` | Tool does not exist on remote node |
| `TELEPORT_PLUGIN_NOT_FOUND` | OBS Teleport plugin not installed |
| `TELEPORT_DIALOG_FAILED` | Teleport dialog UI automation failed |

## Security

- OBS password loaded from `OBS_PASSWORD` environment variable — never hardcoded
- Stream keys are redacted in all tool responses
- No shell execution or arbitrary filesystem access
- Destructive actions (`obs_stop_stream`, `obs_remove_scene`, `obs_remove_rtmp_target`) require explicit `confirmed=true`
- UI automation uses a shared threading lock to prevent race conditions

## Support

If you find this project useful, consider buying me a coffee:

[![Ko-fi](https://img.shields.io/badge/Support%20Me-Ko--fi-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/sidfps)

## License

MIT
