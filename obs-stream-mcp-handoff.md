# obs-stream-mcp — Continuation Prompt

Paste this into a new chat in the same project to resume work.

---

## PROJECT LOCATION
- **Gaming PC**: `C:\Users\Sid\obs-stream-mcp` — GitHub: `git@github.com:sid-fou/obs-stream-mcp.git`
- **Streaming PC (Windows laptop)**: `C:\Users\sidof\obs-stream-mcp` — same repo, SSH remote

## WHAT THIS IS
An MCP server (`obs-stream-mcp`) that controls OBS Studio via WebSocket v5 + UI automation for plugin features. Python 3.11+, obsws-python, official MCP Python SDK, pywinauto for UI automation.

## ARCHITECTURE
```
src/obs_stream_mcp/
├── server.py              # MCP server bootstrap (stdio + background SSE)
├── tools.py               # MCP tool handlers + dispatch + auto-prefixed remote tools
├── schemas.py             # JSON schemas for all tools
├── errors.py              # ErrorCode enum + structured response builders
├── obs_controller.py      # OBS WebSocket v5 controller (all raw OBS calls)
├── obs_ui_controller.py   # UI automation for obs-multi-rtmp plugin (pywinauto)
├── orchestrator.py        # High-level scene builders (gaming, starting soon)
├── layout_loader.py       # Layout preset loader from JSON
├── layouts/default.json   # Transform presets for scene types
├── coordination/
│   ├── __init__.py
│   ├── cluster_manager.py # Cluster config loader + tool implementations
│   └── remote_mcp_client.py # MCP-to-MCP SSE client (ping, list_tools, call_tool)
└── __init__.py
```

## COMPLETED PHASES

### Phase 1: Connection + Scene Control + Streaming
- `obs_connect`, `obs_get_status`, `obs_get_scene_list`, `obs_create_scene`, `obs_switch_scene`
- `obs_start_stream`, `obs_stop_stream` (with confirmation guard)

### Phase 2: Source/Scene Item Management
- `obs_add_source`, `obs_remove_source`, `obs_get_source_list`
- `obs_set_source_transform`, `obs_set_source_visibility`

### Phase 3: Scene Orchestration
- `build_gaming_scene`, `build_starting_soon_scene`
- Rollback safety, layout presets, stream guard

### Phase 4: Diagnostics + Broadcast Management
- `obs_health_check`, `obs_list_devices`
- `obs_get_stream_settings` / `obs_set_stream_settings`

### Phase 4 Extended: Multi-RTMP UI Automation (pywinauto)
- `obs_detect_multi_rtmp_plugin`, `obs_list_rtmp_targets`
- `obs_add_rtmp_target`, `obs_modify_rtmp_target`, `obs_remove_rtmp_target`
- `obs_start_rtmp_target`, `obs_stop_rtmp_target`
- `obs_start_all_rtmp_targets`, `obs_stop_all_rtmp_targets`

### Phase 5: Distributed Cluster Coordination
- `cluster_status`, `cluster_nodes_list`, `cluster_node_status`, `remote_execute`
- **Dual transport**: stdio mode auto-starts SSE server (port 8765) as background daemon thread
- **Auto-registration of prefixed remote tools** (e.g. `gaming_pc__obs_connect`, `streaming_pc__obs_health_check`)
- `obs_remove_scene` tool with confirmation guard
- `cluster_config.json` removed from git tracking; `cluster_config.example.json` committed as template
- Both machines fully set up and tested bidirectionally

## CURRENT STATE — READY FOR PHASE 5 EXTENDED

### What Phase 5 Extended implements: OBS Teleport Plugin Automation
Automates the OBS Teleport plugin across a two-machine setup (gaming PC = host, streaming PC = client).

### Teleport Plugin Discovery (ALREADY DONE — use this knowledge):

**Teleport Host (output side) — gaming PC:**
- Source type `teleport-source` is available in OBS
- Teleport output exists as `Teleport` with kind `teleport-output` in `get_output_list()`
- `set_output_settings('Teleport', {...})` stores settings but does NOT activate the output
- `start_output('Teleport')` succeeds silently but does NOT actually start the teleport service
- The Teleport output can ONLY be activated through the **UI dialog**: Tools → Teleport
- The dialog is a **child window of OBS** (class `OBSBasic`), NOT a top-level window
- To find it: `obs.child_window(title_re='.*Properties.*Teleport.*')`
- **Dialog control map** (descendant indices):
  - `[9]` CheckBox: "Teleport Enabled"
  - `[13]` Edit: Identifier field
  - `[15]` UpDown: TCP Port (default "0" = auto)
  - `[17]` Slider + `[18]` UpDown: Quality (default "90")
  - `[19]` Static: Warning text (only appears when enabled)
  - `[22]` or `[23]` Button: OK (shifts by 1 when warning text appears)
  - `[23]` or `[24]` Button: Cancel
  - `[24]` or `[25]` Button: Defaults
- **Identifier edit**: Use `click_input()` then `type_keys('^a')` then `type_keys('value')` — `set_edit_text()` fails with ElementNotVisible on first open
- **TCP Port**: Is a UpDown/SpinBox, NOT a standalone Edit. Only one Edit is found in the dialog (Identifier). Need to click left of the UpDown to hit its buddy edit area, or use keyboard navigation (Tab to the field).
- OBS may be on a secondary monitor (negative coordinates) — use `click_input()` not raw `mouse.click()`

**Teleport Client (source side) — streaming PC:**
- Source type: `teleport-source`
- Default settings: `{"teleport_list": ""}`
- Add via `obs_add_source(scene, name, "teleport-source", {"teleport_list": "<identifier>"})`
- The `teleport_list` property is how the client selects which host to connect to

**Both machines are now Windows:**
- Gaming PC: Windows 10, OBS 32.0.4, Python 3.13, user `Sid`
- Streaming PC: Windows 11, OBS 32.0.4, Python 3.14, user `sidof`
- pywinauto works on both

### Phase 5 Extended Requirements:
1. Add `teleport_configure_host` tool — opens Tools→Teleport dialog, checks/enables checkbox, sets identifier+port+quality, clicks OK
2. Add `teleport_configure_client` tool — adds teleport-source to a scene on streaming PC
3. Add `teleport_get_status` tool — checks if Teleport output exists and its settings on a given node
4. Add `setup_dual_pc_teleport` orchestrator tool — runs the full workflow:
   - Verify OBS running on both nodes
   - Configure host on gaming PC
   - Configure client on streaming PC (create "Teleport Feed" scene, add teleport-source)
   - Validate connection
5. All UI automation goes in `obs_ui_controller.py` following existing patterns (threading.Lock, structured responses)
6. Do NOT modify existing phase 1-5 tools

## TWO-MACHINE SETUP

### Gaming PC (Windows 10)
- Path: `C:\Users\Sid\obs-stream-mcp`
- OBS Password: `fVbHYnYCMpKxDafc`
- LAN IP: `192.168.1.2`
- SSE port: `8765` (auto-started by dual transport)
- Git remote: SSH (`git@github.com:sid-fou/obs-stream-mcp.git`)
- GPG commit signing enabled

### Streaming PC (Windows 11 laptop)
- Path: `C:\Users\sidof\obs-stream-mcp`
- OBS Password: `RfmAr1qFtJdF8iNv`
- LAN IP: `192.168.1.65`
- SSE port: `8765` (auto-started by dual transport)
- Git remote: SSH (`git@github.com:sid-fou/obs-stream-mcp.git`)
- SSH commit signing enabled
- Git installed via winget, PATH: `C:\Program Files\Git\cmd`

### Cluster configs (local, gitignored):
- Gaming PC `cluster_config.json`: streaming-pc → 192.168.1.65:8765
- Streaming PC `cluster_config.json`: gaming-pc → 192.168.1.2:8765

## KEY LEARNINGS & PITFALLS
- **OBS source names must be unique across ALL scenes** — reusing causes conflict error
- **Never `pkill -f obs_stream_mcp.server`** — kills Claude Desktop's own MCP process (dual transport runs SSE in same process)
- **OBS launch on Windows**: `Start-Process -WorkingDirectory "C:\Program Files\obs-studio\bin\64bit"` — omitting it causes locale errors
- **Teleport dialog is a child of OBS window**, not top-level — use `obs.child_window()` not `d.window()`
- **Desktop Commander on Windows uses PowerShell** — semicolons as separators, PowerShell cmdlets
- **Git on streaming PC needs PATH**: `$env:PATH = "C:\Program Files\Git\cmd;$env:PATH"`

## ERROR CODES (errors.py)
`OBS_NOT_CONNECTED`, `SCENE_NOT_FOUND`, `SOURCE_NOT_FOUND`, `DUPLICATE_SCENE`, `DUPLICATE_SOURCE`, `INVALID_SOURCE_TYPE`, `STREAM_ALREADY_ACTIVE`, `STREAM_NOT_ACTIVE`, `STREAM_GUARD`, `CONFIRMATION_REQUIRED`, `CONNECTION_FAILED`, `INVALID_PARAMETER`, `OBS_ERROR`, `MULTI_RTMP_PLUGIN_NOT_FOUND`, `RTMP_TARGET_NOT_FOUND`, `DUPLICATE_RTMP_TARGET`, `UI_ELEMENT_NOT_FOUND`, `UI_AUTOMATION_FAILED`, `STREAM_START_FAILED`, `NODE_NOT_FOUND`, `NODE_UNREACHABLE`, `REMOTE_TOOL_NOT_FOUND`, `REMOTE_EXECUTION_FAILED`, `CLUSTER_AUTH_FAILED`, `CLUSTER_CONFIG_ERROR`

## DESIGN RULES
- All responses: `{"success": true, "data": {...}}` or `{"success": false, "error": "...", "code": "..."}`
- Never log credentials or expose stream keys
- Validate connection before every operation
- Destructive actions require `confirmed=true`
- Orchestrator NEVER calls OBS WebSocket directly — only through OBSController
- UI controller acquires shared threading.Lock before any UI operation

## GIT LOG (main branch)
```
03f4470 Merge phase-5: Distributed cluster coordination
21cc6b8 Move cluster_config.json to .gitignore, add example template
0ca7a28 Add obs_remove_scene tool with confirmation guard
3095604 Phase 5: Dual transport (stdio+SSE) + auto-register prefixed remote tools
568b333 Phase 5: Distributed cluster coordination - update streaming-pc IP
1bd3fc1 Phase 5: Distributed cluster coordination - tools.py dispatch fix
5c5ed50 Fix: catch and dismiss OBS warning dialogs on target start, add STREAM_START_FAILED error code
b254354 Fix: rewrite dialog field filling + handle delete confirmation QMessageBox
63cf1dd Phase 4 Extended: Multi-RTMP UI automation + pywinauto lazy resolution fix
10b61ef Phase 4: Add broadcast management - get/set stream settings, service presets, key redaction
7b2d5e5 Phase 4: Safety diagnostics, device listing, layout presets, stream guardrails
132478b Phase 3: Scene orchestration - build_gaming_scene, build_starting_soon_scene
b0b4244 Phase 2: Source/scene item management - add, remove, list, transform, visibility
bd0d651 Fix truncated tools.py - restore full call_tool dispatch body
118130c Phase 1: OBS connection, scene control, stream start/stop
```

## WHAT'S NEXT
1. **Phase 5 Extended**: Implement Teleport UI automation (all discovery work done — see above)
2. **Phase 6**: README.md update with full tool documentation
3. **Potential**: Recording control, scene collection management, filter management
