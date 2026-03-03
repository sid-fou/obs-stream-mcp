# obs-stream-mcp

MCP server for controlling OBS Studio via WebSocket v5.

## Requirements

- Python 3.11+
- OBS Studio with WebSocket v5 enabled (port 4455)

## Installation

```bash
pip install -e .
```

## Configuration

Set the OBS WebSocket password via environment variable:

```bash
export OBS_PASSWORD="your-obs-websocket-password"
```

Optional environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `OBS_HOST` | `localhost` | OBS WebSocket host |
| `OBS_PORT` | `4455` | OBS WebSocket port |
| `OBS_PASSWORD` | `""` | OBS WebSocket password |

## Usage

### As an MCP server (stdio)

```bash
obs-stream-mcp
```

### Claude Desktop configuration

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

## Available Tools (Phase 1)

| Tool | Description |
|------|-------------|
| `obs_connect` | Connect to OBS WebSocket |
| `obs_get_status` | Get streaming status |
| `obs_get_scene_list` | List all scenes |
| `obs_create_scene` | Create a new scene |
| `obs_switch_scene` | Switch active scene |
| `obs_start_stream` | Start streaming |
| `obs_stop_stream` | Stop streaming |

## Error Codes

| Code | Description |
|------|-------------|
| `OBS_NOT_CONNECTED` | No active OBS connection |
| `SCENE_NOT_FOUND` | Referenced scene does not exist |
| `SOURCE_NOT_FOUND` | Referenced source does not exist |
| `DUPLICATE_SCENE` | Scene with that name already exists |
| `STREAM_ALREADY_ACTIVE` | Stream is already running |
| `STREAM_NOT_ACTIVE` | Stream is not running |
| `CONNECTION_FAILED` | Could not connect to OBS |
| `INVALID_PARAMETER` | Invalid input parameter |
| `OBS_ERROR` | Unclassified OBS error |

## License

MIT
