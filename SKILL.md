---
name: obs-stream-mcp
description: Controls OBS Studio via WebSocket through the obs-stream-mcp MCP server. Use when the user mentions OBS, streaming, scenes, sources, webcam, game capture, start stream, stop stream, go live, end stream, switch scene, add overlay, add source, remove source, scene layout, stream setup, multi-RTMP, simulcast, Teleport, dual PC, multi PC, cluster, remote OBS, or any request to build, modify, or manage an OBS streaming environment. Do NOT use for general video editing, file conversion, or non-OBS streaming platforms.
metadata:
  author: SID FPS
  version: 2.0.0
  mcp-server: obs-stream-mcp
  category: streaming
  tags: [obs, streaming, scenes, webcam, sources, broadcast, multi-rtmp, teleport, dual-pc, cluster]
---

# OBS Stream MCP Skill

Controls OBS Studio via the obs-stream-mcp MCP server. This skill enforces strict behavioral guardrails to ensure Claude makes only the changes the user explicitly requested, confirms destructive actions, and never assumes scene state.

Covers: scene/source management, streaming, scene orchestration, multi-RTMP broadcasting, OBS Teleport dual-PC video feeds, and distributed multi-machine cluster control.

---

## Critical Rules

These rules override all other behavior when this skill is active.

### Rule 1: Always Check OBS Status First

Before ANY operation, call `obs_connect` then `obs_get_status` to confirm OBS is connected and responsive.

- If OBS is not connected or the call fails, STOP immediately. Do not attempt further tool calls.
- Instruct the user: "OBS is not connected. Please ensure OBS is running with the WebSocket server enabled, then try again."
- Do not guess or assume OBS state.
- For remote machines, use the prefixed version (e.g. `streaming_pc__obs_connect`).

### Rule 2: Minimal Modification Doctrine

Claude must modify ONLY what the user explicitly requested. Nothing more.

- NEVER remove, replace, reorder, or restructure sources the user did not mention.
- NEVER rebuild or recreate a scene unless the user explicitly says "rebuild", "recreate", or "start from scratch".
- Prefer ADDITIVE changes. Adding a source is safe. Removing or replacing is destructive.
- When editing a scene, leave all untouched sources exactly as they are — position, transform, visibility, and order.
- If the user says "add a webcam to my gaming scene", add the webcam source. Do not touch anything else in the scene.

### Rule 3: Confirmation Before Destructive Actions

Always ask for explicit yes/no confirmation before:

- `obs_stop_stream` — "You are currently live. Are you sure you want to stop the stream? (yes/no)"
- `obs_remove_source` — "This will remove [source name] from [scene name]. Confirm? (yes/no)"
- `obs_remove_scene` — "This will delete the scene [name]. Confirm? (yes/no)"
- `obs_remove_rtmp_target` — "This will remove the RTMP target [name]. Confirm? (yes/no)"
- Overwriting an existing scene — "A scene named [name] already exists. Overwrite it? (yes/no)"
- Bulk modifications (3+ changes) — Summarize all planned changes and ask: "Proceed? (yes/no)"

Do NOT proceed until the user responds affirmatively.

### Rule 4: Validate Before Acting

- Before `obs_switch_scene`: call `obs_get_scene_list` and confirm the target scene exists.
- Before editing a scene: call `obs_get_source_list` for that scene to know current state.
- Before creating a scene: call `obs_get_scene_list` to check for duplicate names.
- If a target scene or source does not exist, inform the user and ask how to proceed. Do not create or substitute automatically.

### Rule 5: Never Expose Credentials

- Never include OBS passwords or stream keys in responses.
- If a tool response contains sensitive data, redact it before presenting to the user.
- Stream keys are already redacted by the server, but always double-check.

---

## Available Tools

### Connection & Status

- `obs_connect` — Connect to OBS WebSocket. **Must be called first** before any other tool.
- `obs_get_status` — Get connection and streaming status.
- `obs_health_check` — Full diagnostics: connection, streaming, recording, version, latency.
- `obs_list_devices` — List available video and audio capture devices (prevents device name guessing).

### Scene Management

- `obs_get_scene_list` — List all scenes and the current active scene. Use for validation.
- `obs_create_scene` — Create a new empty scene.
- `obs_remove_scene` — Remove a scene. Requires `confirmed=true`. Cannot remove the active scene.
- `obs_switch_scene` — Switch the active program scene.

### Source Management

- `obs_add_source` — Add a source to a scene. Common types: `image_source`, `color_source_v3`, `browser_source`, `ffmpeg_source`, `text_gdiplus_v3`, `monitor_capture`, `window_capture`, `game_capture`, `dshow_input`.
- `obs_remove_source` — Remove a source from a scene. Always confirm first.
- `obs_get_source_list` — List all sources in a scene with properties. Use before editing.
- `obs_set_source_transform` — Set position, scale, rotation, crop, bounds on a source.
- `obs_set_source_visibility` — Show or hide a source in a scene.

### Streaming

- `obs_get_stream_settings` — Get stream service config (key is always redacted).
- `obs_set_stream_settings` — Configure stream service. Presets: `youtube`, `twitch`, `kick`, or custom RTMP URL.
- `obs_start_stream` — Start streaming.
- `obs_stop_stream` — Stop streaming. Requires `confirmed=true`.

### Scene Orchestration (High-Level)

Prefer these for complete setups. They handle source creation, positioning, and rollback.

- `build_gaming_scene` — Build a complete gaming scene (Game Capture, Display Capture, Webcam, Title overlay). Use when user asks to "set up a gaming scene" or "build my stream layout".
- `build_starting_soon_scene` — Build a "Starting Soon" scene with background, optional image, optional countdown, and title text.

### Multi-RTMP Broadcasting (requires obs-multi-rtmp plugin)

- `obs_detect_multi_rtmp_plugin` — Check if the plugin is installed and visible.
- `obs_list_rtmp_targets` — List all configured RTMP targets with active/inactive state.
- `obs_add_rtmp_target` — Add a new RTMP target (name, server URL, stream key).
- `obs_modify_rtmp_target` — Modify an existing target's settings.
- `obs_remove_rtmp_target` — Remove a target. Requires `confirmed=true`.

- `obs_start_rtmp_target` — Start streaming to a specific target (main OBS stream must be running).
- `obs_stop_rtmp_target` — Stop a specific target.
- `obs_start_all_rtmp_targets` — Start all targets simultaneously.
- `obs_stop_all_rtmp_targets` — Stop all active targets. Requires `confirmed=true`.

### OBS Teleport (requires OBS Teleport plugin)

Used for zero-latency video feeds between two PCs (e.g. gaming PC → streaming PC).

- `teleport_configure_host` — Enable/configure Teleport output on the sender machine. Uses UI automation to toggle the checkbox, set identifier, port, and quality.
- `teleport_configure_client` — Add a Teleport source on the receiver machine. Creates the scene and source, opens the properties dialog, clicks Refresh List, and selects the host from the dropdown — all automated.
- `teleport_get_status` — Check Teleport output status via WebSocket (no UI automation needed).
- `setup_dual_pc_teleport` — Orchestrate full dual-PC Teleport setup across cluster nodes in one call.

### Distributed Cluster Coordination

For controlling OBS on multiple machines from a single Claude Desktop instance.

- `cluster_status` — Check reachability of all cluster nodes (online/offline).
- `cluster_nodes_list` — List all configured nodes with host and port.
- `cluster_node_status` — Detailed status of a specific node.
- `remote_execute` — Execute any MCP tool on a remote node.

All base tools are also available with node prefixes (e.g. `streaming_pc__obs_connect`, `streaming_pc__build_gaming_scene`, `streaming_pc__teleport_configure_client`).

---

## Workflow Sequencing

All operations follow a deterministic sequence. Do not skip steps.

### Starting a Stream

1. Call `obs_connect` — ensure connection.
2. Call `obs_get_scene_list` — confirm at least one scene exists.
3. If the user specified a scene, call `obs_switch_scene` to activate it.
4. Call `obs_start_stream`.
5. Confirm to the user: "Stream is live on [scene name]."

### Stopping a Stream

1. Call `obs_get_status` — confirm OBS is connected and streaming.
2. Ask for confirmation: "You are currently live. Stop the stream? (yes/no)"
3. On confirmation, call `obs_stop_stream` with `confirmed=true`.
4. Confirm: "Stream stopped."

### Building a Scene

1. Call `obs_connect`.
2. Call `obs_get_scene_list` — check for duplicate names.
3. If duplicate found, ask: "A scene named [name] already exists. Overwrite it, or use a different name?"
4. Use `build_gaming_scene` if the request matches a standard gaming layout.
5. Otherwise, use `obs_create_scene` followed by individual `obs_add_source` calls.
6. Confirm the final source list to the user.

### Adding a Source to an Existing Scene

1. Call `obs_get_source_list` for the target scene — confirm scene exists and inspect current sources.
2. Call `obs_add_source` with the requested source only.
3. If positioning is requested, call `obs_set_source_transform`.
4. Confirm: "Added [source] to [scene]. No other sources were modified."

### Setting Up Multi-RTMP Simulcast

1. Call `obs_detect_multi_rtmp_plugin` — confirm plugin is installed.
2. Call `obs_list_rtmp_targets` — check existing targets.
3. For each platform, call `obs_add_rtmp_target` with name, server URL, and stream key.
4. Call `obs_start_stream` to start the main OBS stream (required for shared encoder).
5. Call `obs_start_all_rtmp_targets` to begin simulcasting.
6. Confirm: "Now streaming to [platform list]."

### Setting Up Dual-PC Teleport

For sending video from a gaming PC to a streaming PC:

1. Call `obs_connect` on both machines (local + `streaming_pc__obs_connect`).
2. Call `teleport_configure_host` on the gaming PC (sender) with `enabled=true`.
3. Call `streaming_pc__teleport_configure_client` on the streaming PC (receiver) with the same identifier.
4. The client tool automatically: creates the scene, adds the source, opens properties, clicks Refresh List, selects the host from the dropdown, and clicks OK.
5. Confirm: "Teleport configured. Gaming PC feed is available on the streaming PC."
6. Note: OBS on the streaming PC may need a restart after the first Teleport connection to display the feed.

Alternatively, use `setup_dual_pc_teleport` to orchestrate all steps in a single call.

### Switching Scenes

1. Call `obs_get_scene_list`.
2. Confirm the target scene exists. If not, list available scenes and ask the user to choose.
3. Call `obs_switch_scene`.
4. Confirm: "Switched to [scene name]."

---

## Partial Failure and Rollback

If a multi-step workflow fails partway through:

1. STOP further tool calls immediately.
2. Report exactly what succeeded and what failed.
3. Provide rollback guidance: list the manual steps the user can take to undo completed actions.
4. Ask the user how to proceed before retrying.

---

## Troubleshooting

### OBS Not Connected
"Please ensure OBS Studio is running with the WebSocket server enabled (Tools > WebSocket Server Settings). Verify the port and password match your MCP server configuration."

### Device Not Found
"The requested device was not found. Check that it is connected and available in system settings. Close any other applications that may be using it."

### Scene Not Found
Call `obs_get_scene_list`, present available scenes, and ask the user to confirm or correct the name.

### Stream Start Failure
"Stream failed to start. Verify your stream key and output settings in OBS (Settings > Stream). Check network connectivity."

### Duplicate Scene Name
Always check `obs_get_scene_list` first. Ask: "A scene named [name] already exists. Overwrite it, or choose a different name?"

### Multi-RTMP Target Start Failure
The main OBS stream must be running before RTMP targets can start (shared encoder). Call `obs_start_stream` first.

### Teleport Feed Not Visible
After the first Teleport connection, OBS on the receiving PC may need a restart to display the video feed. This is a known OBS Teleport behavior.

### Remote Node Unreachable
Check that OBS and the MCP server are running on the remote machine, that the SSE server is listening on port 8765, and that the machines can reach each other on the LAN.
