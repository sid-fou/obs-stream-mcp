"""UI automation controller for OBS plugin interactions.

Uses Windows UI Automation (UIA) via pywinauto to control plugin UI elements
that are not accessible through the OBS WebSocket API.

Restricted to plugin configuration only (e.g., Multiple RTMP Outputs).
Does NOT replace any existing WebSocket functionality.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from pywinauto import Desktop
from pywinauto.timings import TimeoutError as UITimeoutError

from obs_stream_mcp.errors import (
    ErrorCode,
    error_response,
    success_response,
)


class OBSUIController:
    """Controls OBS plugin UI elements via Windows UI Automation.

    All public methods return structured JSON dicts matching the project
    convention: {success: true, data: {...}} or {success: false, error: ..., code: ...}.

    Thread-safe: acquires a shared lock before any UI operation to prevent
    concurrent UI automation and WebSocket scene/stream control.
    """

    # Timeout (seconds) waiting for UI elements to appear.
    _ELEMENT_TIMEOUT = 5
    # Short pause between UI actions for stability.
    _ACTION_DELAY = 0.3

    def __init__(self, ui_lock: threading.Lock | None = None) -> None:
        self._lock = ui_lock or threading.Lock()
        self._desktop = Desktop(backend="uia")

    @property
    def lock(self) -> threading.Lock:
        """Shared lock for coordinating with WebSocket operations."""
        return self._lock

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_obs_window(self):
        """Locate the main OBS Studio window."""
        try:
            win = self._desktop.window(class_name="OBSBasic")
            # Force resolution — pywinauto returns a lazy spec that doesn't
            # raise until you access a property.
            if win.exists():
                return win
            return None
        except Exception:
            return None

    def _find_multi_rtmp_dock(self, obs_win):
        """Locate the Multiple Output dock within OBS."""
        try:
            dock = obs_win.child_window(
                title="Multiple output", class_name="OBSDock"
            )
            if dock.exists():
                return dock
            return None
        except Exception:
            return None

    def _find_scroll_viewport(self, dock):
        """Find the scroll area viewport within the dock."""
        try:
            scroll = dock.child_window(class_name="QScrollArea")
            if not scroll.exists():
                return None
            # The viewport is the first QWidget child of the scroll area
            viewport = scroll.child_window(class_name="QWidget", found_index=0)
            if not viewport.exists():
                return None
            return viewport
        except Exception:
            return None

    def _find_target_widget(self, dock, target_name: str):
        """Find a specific target's push-widget group by its name label.

        Returns the GroupBox element for the target, or None.
        """
        viewport = self._find_scroll_viewport(dock)
        if viewport is None:
            return None

        # Get the main container inside viewport
        try:
            container = viewport.child_window(class_name="QWidget", found_index=0)
        except Exception:
            return None

        # Iterate through children looking for push-widget groups
        for child in container.children():
            auto_id = child.element_info.automation_id or ""
            if "push-widget" not in auto_id:
                continue
            # Check the first QLabel for the target name
            labels = child.children(class_name="QLabel")
            for label in labels:
                if label.window_text() == target_name:
                    return child
        return None

    def _find_target_button(self, target_widget, button_text: str):
        """Find a button within a target widget by its text."""
        buttons = target_widget.children(class_name="QPushButton")
        for btn in buttons:
            if btn.window_text() == button_text:
                return btn
        return None

    def _get_target_status(self, target_widget) -> dict[str, Any]:
        """Extract status info from a target widget."""
        labels = target_widget.children(class_name="QLabel")
        name = ""
        status_text = ""
        for i, label in enumerate(labels):
            text = label.window_text()
            if i == 0:
                name = text
            else:
                status_text = text

        # Determine state from button text
        buttons = target_widget.children(class_name="QPushButton")
        button_texts = [b.window_text() for b in buttons]
        is_active = "Stop" in button_texts

        return {
            "name": name,
            "active": is_active,
            "status_text": status_text,
        }

    def _list_all_targets(self, dock) -> list[dict[str, Any]]:
        """List all targets from the dock UI."""
        viewport = self._find_scroll_viewport(dock)
        if viewport is None:
            return []

        try:
            container = viewport.child_window(class_name="QWidget", found_index=0)
            if not container.exists():
                return []
        except Exception:
            return []

        targets = []
        try:
            for child in container.children():
                auto_id = child.element_info.automation_id or ""
                if "push-widget" not in auto_id:
                    continue
                info = self._get_target_status(child)
                if info["name"]:
                    targets.append(info)
        except Exception:
            pass
        return targets

    def _wait_for_dialog(self, obs_win, title: str, timeout: float = 5.0):
        """Wait for a dialog to appear as a child of OBS."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                dlg = obs_win.child_window(title=title, class_name="QDialog")
                if dlg.exists():
                    return dlg
            except Exception:
                pass
            time.sleep(0.2)
        return None

    def _dismiss_warning_dialog(self, obs_win, timeout: float = 2.0) -> str | None:
        """Check for and dismiss a Warning/Error QMessageBox.

        Returns the warning message text if a dialog was found and dismissed,
        or None if no dialog appeared.
        """
        try:
            for title in ("Warning", "Error"):
                msgbox = obs_win.child_window(title=title, class_name="QMessageBox")
                if msgbox.exists(timeout=timeout):
                    # Extract the message text.
                    msg = ""
                    try:
                        label = msgbox.child_window(control_type="Text", found_index=0)
                        msg = label.window_text()
                    except Exception:
                        msg = f"{title} dialog appeared"
                    # Dismiss it.
                    try:
                        ok_btn = msgbox.child_window(title="OK", class_name="QPushButton")
                        ok_btn.click_input()
                        time.sleep(self._ACTION_DELAY)
                    except Exception:
                        import pywinauto.keyboard
                        pywinauto.keyboard.send_keys("{ENTER}")
                        time.sleep(self._ACTION_DELAY)
                    return msg
        except Exception:
            pass
        return None

    def _wait_for_dialog_close(self, obs_win, title: str, timeout: float = 5.0) -> bool:
        """Wait for a dialog to close."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                dlg = obs_win.child_window(title=title, class_name="QDialog")
                if not dlg.exists():
                    return True
            except Exception:
                return True
            time.sleep(0.2)
        return False

    def _fill_streaming_dialog(
        self,
        dialog,
        name: str | None = None,
        server: str | None = None,
        stream_key: str | None = None,
    ) -> dict[str, Any] | None:
        """Fill the Streaming Settings dialog fields.

        Returns None on success, or an error_response dict on failure.

        Dialog layout (obs-multi-rtmp plugin):
          Edit[0] = Name       (direct child of main scroll content)
          Edit[1] = URL        (inside Service tab stacked widget)
          Edit[2] = Stream Key (inside Service tab stacked widget)
          Edit[3] = Resolution (inside Video Settings group — ignored)
        """
        try:
            all_edits = dialog.descendants(control_type="Edit")
        except Exception:
            return error_response(
                ErrorCode.UI_ELEMENT_NOT_FOUND,
                "Could not enumerate edit fields in dialog",
            )

        if len(all_edits) < 3:
            return error_response(
                ErrorCode.UI_ELEMENT_NOT_FOUND,
                f"Expected at least 3 edit fields in dialog, found {len(all_edits)}",
            )

        name_field = all_edits[0]
        url_field = all_edits[1]
        key_field = all_edits[2]

        def _set_field(field, value: str) -> dict[str, Any] | None:
            try:
                field.click_input()
                field.type_keys("^a", pause=0.05)
                field.type_keys(value, with_spaces=True, pause=0.02)
                time.sleep(self._ACTION_DELAY)
                return None
            except Exception as exc:
                return error_response(
                    ErrorCode.UI_AUTOMATION_FAILED,
                    f"Failed to set field value: {exc}",
                )

        if name is not None:
            err = _set_field(name_field, name)
            if err:
                return err

        # Ensure Service tab is selected before filling URL/key.
        if server is not None or stream_key is not None:
            try:
                tab_bar = dialog.child_window(control_type="Tab")
                service_tab = tab_bar.child_window(title="Service", control_type="TabItem")
                service_tab.click_input()
                time.sleep(self._ACTION_DELAY)
            except Exception:
                pass  # May already be selected or only one tab

            if server is not None:
                err = _set_field(url_field, server)
                if err:
                    return err

            if stream_key is not None:
                err = _set_field(key_field, stream_key)
                if err:
                    return err

        return None  # Success

    # ------------------------------------------------------------------
    # Public API: Detection
    # ------------------------------------------------------------------

    def detect_plugin(self) -> dict[str, Any]:
        """Check if the Multiple RTMP Outputs plugin dock is present in OBS."""
        with self._lock:
            obs = self._find_obs_window()
            if obs is None:
                return error_response(
                    ErrorCode.OBS_NOT_CONNECTED,
                    "OBS Studio window not found",
                )

            dock = self._find_multi_rtmp_dock(obs)
            if dock is None:
                return error_response(
                    ErrorCode.MULTI_RTMP_PLUGIN_NOT_FOUND,
                    "Multiple RTMP Outputs plugin dock not found. "
                    "Ensure the obs-multi-rtmp plugin is installed and the dock is visible.",
                )

            targets = self._list_all_targets(dock)
            return success_response({
                "plugin_detected": True,
                "dock_title": "Multiple output",
                "target_count": len(targets),
            })

    # ------------------------------------------------------------------
    # Public API: List targets
    # ------------------------------------------------------------------

    def list_rtmp_targets(self) -> dict[str, Any]:
        """List all configured RTMP targets from the Multi-Output dock."""
        with self._lock:
            obs = self._find_obs_window()
            if obs is None:
                return error_response(
                    ErrorCode.OBS_NOT_CONNECTED,
                    "OBS Studio window not found",
                )

            dock = self._find_multi_rtmp_dock(obs)
            if dock is None:
                return error_response(
                    ErrorCode.MULTI_RTMP_PLUGIN_NOT_FOUND,
                    "Multiple RTMP Outputs plugin dock not found",
                )

            targets = self._list_all_targets(dock)
            # Redact any key info — only names and states
            return success_response({
                "targets": targets,
                "count": len(targets),
            })

    # ------------------------------------------------------------------
    # Public API: Add target
    # ------------------------------------------------------------------

    def add_rtmp_target(
        self,
        name: str,
        server: str,
        stream_key: str,
    ) -> dict[str, Any]:
        """Add a new RTMP target via the plugin UI dialog.

        Opens the 'Add new target' dialog, fills in Name, URL, and Stream key,
        then clicks OK.
        """
        if not name or not name.strip():
            return error_response(ErrorCode.INVALID_PARAMETER, "name must not be empty")
        if not server or not server.strip():
            return error_response(ErrorCode.INVALID_PARAMETER, "server must not be empty")
        if not stream_key or not stream_key.strip():
            return error_response(ErrorCode.INVALID_PARAMETER, "stream_key must not be empty")

        with self._lock:
            obs = self._find_obs_window()
            if obs is None:
                return error_response(ErrorCode.OBS_NOT_CONNECTED, "OBS Studio window not found")

            dock = self._find_multi_rtmp_dock(obs)
            if dock is None:
                return error_response(ErrorCode.MULTI_RTMP_PLUGIN_NOT_FOUND, "Multiple RTMP Outputs plugin dock not found")

            # Check for duplicate name
            existing = self._list_all_targets(dock)
            if any(t["name"] == name for t in existing):
                return error_response(
                    ErrorCode.DUPLICATE_RTMP_TARGET,
                    f"RTMP target '{name}' already exists",
                )

            # Click "Add new target"
            try:
                add_btn = dock.child_window(title="Add new target", control_type="Button")
                add_btn.click_input()
                time.sleep(self._ACTION_DELAY)
            except Exception as e:
                return error_response(ErrorCode.UI_AUTOMATION_FAILED, f"Failed to click 'Add new target': {e}")

            # Wait for dialog
            dialog = self._wait_for_dialog(obs, "Streaming Settings")
            if dialog is None:
                return error_response(ErrorCode.UI_AUTOMATION_FAILED, "Streaming Settings dialog did not open")

            # Fill the dialog
            err = self._fill_streaming_dialog(dialog, name=name, server=server, stream_key=stream_key)
            if err:
                # Close dialog on error
                try:
                    import pywinauto.keyboard
                    pywinauto.keyboard.send_keys("{ESC}")
                except Exception:
                    pass
                return err

            # Click OK
            try:
                ok_btn = dialog.child_window(title="OK", class_name="QPushButton")
                ok_btn.click_input()
                time.sleep(self._ACTION_DELAY)
            except Exception as e:
                return error_response(ErrorCode.UI_AUTOMATION_FAILED, f"Failed to click OK: {e}")

            # Wait for dialog to close
            self._wait_for_dialog_close(obs, "Streaming Settings")

            # Verify target was added
            updated = self._list_all_targets(dock)
            if any(t["name"] == name for t in updated):
                return success_response({
                    "target_name": name,
                    "server": server,
                    "stream_key_set": True,
                    "total_targets": len(updated),
                })
            else:
                return error_response(
                    ErrorCode.UI_AUTOMATION_FAILED,
                    f"Target '{name}' was not found after dialog closed — add may have failed",
                )

    # ------------------------------------------------------------------
    # Public API: Modify target
    # ------------------------------------------------------------------

    def modify_rtmp_target(
        self,
        target_name: str,
        new_name: str | None = None,
        server: str | None = None,
        stream_key: str | None = None,
    ) -> dict[str, Any]:
        """Modify an existing RTMP target via the plugin UI dialog.

        Opens the 'Modify' dialog for the named target, updates provided fields,
        then clicks OK. Only provided fields are changed.
        """
        if not target_name or not target_name.strip():
            return error_response(ErrorCode.INVALID_PARAMETER, "target_name must not be empty")

        if new_name is None and server is None and stream_key is None:
            return error_response(ErrorCode.INVALID_PARAMETER, "At least one field to modify must be provided")

        with self._lock:
            obs = self._find_obs_window()
            if obs is None:
                return error_response(ErrorCode.OBS_NOT_CONNECTED, "OBS Studio window not found")

            dock = self._find_multi_rtmp_dock(obs)
            if dock is None:
                return error_response(ErrorCode.MULTI_RTMP_PLUGIN_NOT_FOUND, "Multiple RTMP Outputs plugin dock not found")

            widget = self._find_target_widget(dock, target_name)
            if widget is None:
                return error_response(
                    ErrorCode.RTMP_TARGET_NOT_FOUND,
                    f"RTMP target '{target_name}' not found in dock",
                )

            # Check for duplicate if renaming
            if new_name and new_name != target_name:
                existing = self._list_all_targets(dock)
                if any(t["name"] == new_name for t in existing):
                    return error_response(
                        ErrorCode.DUPLICATE_RTMP_TARGET,
                        f"RTMP target '{new_name}' already exists",
                    )

            # Click Modify button
            modify_btn = self._find_target_button(widget, "Modify")
            if modify_btn is None:
                return error_response(ErrorCode.UI_ELEMENT_NOT_FOUND, "Modify button not found")

            try:
                modify_btn.click_input()
                time.sleep(self._ACTION_DELAY)
            except Exception as e:
                return error_response(ErrorCode.UI_AUTOMATION_FAILED, f"Failed to click Modify: {e}")

            # Wait for dialog
            dialog = self._wait_for_dialog(obs, "Streaming Settings")
            if dialog is None:
                return error_response(ErrorCode.UI_AUTOMATION_FAILED, "Streaming Settings dialog did not open")

            # Fill fields
            err = self._fill_streaming_dialog(dialog, name=new_name, server=server, stream_key=stream_key)
            if err:
                try:
                    import pywinauto.keyboard
                    pywinauto.keyboard.send_keys("{ESC}")
                except Exception:
                    pass
                return err

            # Click OK
            try:
                ok_btn = dialog.child_window(title="OK", class_name="QPushButton")
                ok_btn.click_input()
                time.sleep(self._ACTION_DELAY)
            except Exception as e:
                return error_response(ErrorCode.UI_AUTOMATION_FAILED, f"Failed to click OK: {e}")

            self._wait_for_dialog_close(obs, "Streaming Settings")

            final_name = new_name if new_name else target_name
            return success_response({
                "target_name": final_name,
                "modified": True,
                "server_updated": server is not None,
                "stream_key_updated": stream_key is not None,
                "name_updated": new_name is not None and new_name != target_name,
            })

    # ------------------------------------------------------------------
    # Public API: Remove target
    # ------------------------------------------------------------------

    def remove_rtmp_target(self, target_name: str, confirmed: bool = False) -> dict[str, Any]:
        """Remove an RTMP target via the plugin UI.

        Requires confirmed=True to prevent accidental deletion.
        """
        if not target_name or not target_name.strip():
            return error_response(ErrorCode.INVALID_PARAMETER, "target_name must not be empty")

        if not confirmed:
            return error_response(
                ErrorCode.CONFIRMATION_REQUIRED,
                f"Removing RTMP target '{target_name}' requires confirmed=true",
            )

        with self._lock:
            obs = self._find_obs_window()
            if obs is None:
                return error_response(ErrorCode.OBS_NOT_CONNECTED, "OBS Studio window not found")

            dock = self._find_multi_rtmp_dock(obs)
            if dock is None:
                return error_response(ErrorCode.MULTI_RTMP_PLUGIN_NOT_FOUND, "Multiple RTMP Outputs plugin dock not found")

            widget = self._find_target_widget(dock, target_name)
            if widget is None:
                return error_response(
                    ErrorCode.RTMP_TARGET_NOT_FOUND,
                    f"RTMP target '{target_name}' not found in dock",
                )

            delete_btn = self._find_target_button(widget, "Delete")
            if delete_btn is None:
                return error_response(ErrorCode.UI_ELEMENT_NOT_FOUND, "Delete button not found")

            try:
                delete_btn.click_input()
                time.sleep(self._ACTION_DELAY)
            except Exception as e:
                return error_response(ErrorCode.UI_AUTOMATION_FAILED, f"Failed to click Delete: {e}")

            # The plugin shows a "Question" confirmation dialog — click Yes.
            try:
                msgbox = obs.child_window(title="Question", class_name="QMessageBox")
                if msgbox.exists(timeout=2):
                    yes_btn = msgbox.child_window(title="Yes", class_name="QPushButton")
                    yes_btn.click_input()
                    time.sleep(self._ACTION_DELAY)
            except Exception:
                pass  # No confirmation dialog appeared, deletion may have proceeded

            # Verify removal
            time.sleep(0.5)
            updated = self._list_all_targets(dock)
            removed = not any(t["name"] == target_name for t in updated)
            if removed:
                return success_response({
                    "target_name": target_name,
                    "removed": True,
                    "remaining_targets": len(updated),
                })
            else:
                return error_response(
                    ErrorCode.UI_AUTOMATION_FAILED,
                    f"Target '{target_name}' still present after delete — a confirmation dialog may have appeared",
                )

    # ------------------------------------------------------------------
    # Public API: Start / Stop individual targets
    # ------------------------------------------------------------------

    def start_rtmp_target(self, target_name: str) -> dict[str, Any]:
        """Start streaming for a specific RTMP target.

        The main OBS stream must be running first (shared encoder requirement).
        """
        if not target_name or not target_name.strip():
            return error_response(ErrorCode.INVALID_PARAMETER, "target_name must not be empty")

        with self._lock:
            obs = self._find_obs_window()
            if obs is None:
                return error_response(ErrorCode.OBS_NOT_CONNECTED, "OBS Studio window not found")

            dock = self._find_multi_rtmp_dock(obs)
            if dock is None:
                return error_response(ErrorCode.MULTI_RTMP_PLUGIN_NOT_FOUND, "Multiple RTMP Outputs plugin dock not found")

            widget = self._find_target_widget(dock, target_name)
            if widget is None:
                return error_response(
                    ErrorCode.RTMP_TARGET_NOT_FOUND,
                    f"RTMP target '{target_name}' not found in dock",
                )

            # Check if already active
            status = self._get_target_status(widget)
            if status["active"]:
                return error_response(
                    ErrorCode.STREAM_ALREADY_ACTIVE,
                    f"RTMP target '{target_name}' is already streaming",
                )

            start_btn = self._find_target_button(widget, "Start")
            if start_btn is None:
                return error_response(ErrorCode.UI_ELEMENT_NOT_FOUND, "Start button not found")

            try:
                start_btn.click_input()
            except Exception as e:
                return error_response(ErrorCode.UI_AUTOMATION_FAILED, f"Failed to click Start: {e}")

            # Check for warning dialog (e.g., encoder not available).
            warning_msg = self._dismiss_warning_dialog(obs, timeout=1.5)
            if warning_msg:
                return error_response(
                    ErrorCode.STREAM_START_FAILED,
                    f"OBS refused to start target '{target_name}': {warning_msg}",
                )

            # Wait briefly and check status
            time.sleep(1.5)
            try:
                updated_status = self._get_target_status(widget)
            except Exception:
                # Widget may have refreshed; re-find it
                widget = self._find_target_widget(dock, target_name)
                if widget is None:
                    return success_response({
                        "target_name": target_name,
                        "action": "start",
                        "note": "Start clicked but target widget could not be re-found for verification",
                    })
                updated_status = self._get_target_status(widget)

            if updated_status["active"]:
                return success_response({
                    "target_name": target_name,
                    "active": True,
                    "status_text": updated_status["status_text"],
                })
            else:
                # Start may have failed (e.g., connection error)
                return error_response(
                    ErrorCode.UI_AUTOMATION_FAILED,
                    f"Target '{target_name}' failed to start. "
                    f"Status: {updated_status['status_text'] or 'unknown'}",
                )

    def stop_rtmp_target(self, target_name: str, confirmed: bool = False) -> dict[str, Any]:
        """Stop streaming for a specific RTMP target.

        Requires confirmed=True to prevent accidental stops.
        """
        if not target_name or not target_name.strip():
            return error_response(ErrorCode.INVALID_PARAMETER, "target_name must not be empty")

        if not confirmed:
            return error_response(
                ErrorCode.CONFIRMATION_REQUIRED,
                f"Stopping RTMP target '{target_name}' requires confirmed=true",
            )

        with self._lock:
            obs = self._find_obs_window()
            if obs is None:
                return error_response(ErrorCode.OBS_NOT_CONNECTED, "OBS Studio window not found")

            dock = self._find_multi_rtmp_dock(obs)
            if dock is None:
                return error_response(ErrorCode.MULTI_RTMP_PLUGIN_NOT_FOUND, "Multiple RTMP Outputs plugin dock not found")

            widget = self._find_target_widget(dock, target_name)
            if widget is None:
                return error_response(
                    ErrorCode.RTMP_TARGET_NOT_FOUND,
                    f"RTMP target '{target_name}' not found in dock",
                )

            status = self._get_target_status(widget)
            if not status["active"]:
                return error_response(
                    ErrorCode.STREAM_NOT_ACTIVE,
                    f"RTMP target '{target_name}' is not streaming",
                )

            stop_btn = self._find_target_button(widget, "Stop")
            if stop_btn is None:
                return error_response(ErrorCode.UI_ELEMENT_NOT_FOUND, "Stop button not found")

            try:
                stop_btn.click_input()
            except Exception as e:
                return error_response(ErrorCode.UI_AUTOMATION_FAILED, f"Failed to click Stop: {e}")

            time.sleep(1.0)
            try:
                updated_status = self._get_target_status(widget)
            except Exception:
                widget = self._find_target_widget(dock, target_name)
                if widget is None:
                    return success_response({
                        "target_name": target_name,
                        "action": "stop",
                        "note": "Stop clicked but target widget could not be re-found for verification",
                    })
                updated_status = self._get_target_status(widget)

            return success_response({
                "target_name": target_name,
                "active": updated_status["active"],
                "status_text": updated_status["status_text"],
            })

    # ------------------------------------------------------------------
    # Public API: Start / Stop all targets
    # ------------------------------------------------------------------

    def start_all_rtmp_targets(self) -> dict[str, Any]:
        """Start all RTMP targets via the 'Start all' button."""
        with self._lock:
            obs = self._find_obs_window()
            if obs is None:
                return error_response(ErrorCode.OBS_NOT_CONNECTED, "OBS Studio window not found")

            dock = self._find_multi_rtmp_dock(obs)
            if dock is None:
                return error_response(ErrorCode.MULTI_RTMP_PLUGIN_NOT_FOUND, "Multiple RTMP Outputs plugin dock not found")

            try:
                start_all_btn = dock.child_window(title="Start all", control_type="Button")
                start_all_btn.click_input()
            except Exception as e:
                return error_response(ErrorCode.UI_AUTOMATION_FAILED, f"Failed to click 'Start all': {e}")

            # Check for warning dialog (e.g., encoder not available).
            warning_msg = self._dismiss_warning_dialog(obs, timeout=1.5)
            if warning_msg:
                return error_response(
                    ErrorCode.STREAM_START_FAILED,
                    f"OBS refused to start targets: {warning_msg}",
                )

            time.sleep(2.0)
            targets = self._list_all_targets(dock)
            return success_response({
                "action": "start_all",
                "targets": targets,
            })

    def stop_all_rtmp_targets(self, confirmed: bool = False) -> dict[str, Any]:
        """Stop all RTMP targets via the 'Stop all' button.

        Requires confirmed=True to prevent accidental stops.
        """
        if not confirmed:
            return error_response(
                ErrorCode.CONFIRMATION_REQUIRED,
                "Stopping all RTMP targets requires confirmed=true",
            )

        with self._lock:
            obs = self._find_obs_window()
            if obs is None:
                return error_response(ErrorCode.OBS_NOT_CONNECTED, "OBS Studio window not found")

            dock = self._find_multi_rtmp_dock(obs)
            if dock is None:
                return error_response(ErrorCode.MULTI_RTMP_PLUGIN_NOT_FOUND, "Multiple RTMP Outputs plugin dock not found")

            try:
                stop_all_btn = dock.child_window(title="Stop all", control_type="Button")
                stop_all_btn.click_input()
            except Exception as e:
                return error_response(ErrorCode.UI_AUTOMATION_FAILED, f"Failed to click 'Stop all': {e}")

            time.sleep(2.0)
            targets = self._list_all_targets(dock)
            return success_response({
                "action": "stop_all",
                "targets": targets,
            })

    # ------------------------------------------------------------------
    # Internal helpers: Teleport plugin
    # ------------------------------------------------------------------

    def _open_teleport_dialog(self, obs_win):
        """Open Tools -> Teleport dialog in OBS.

        Returns the dialog wrapper, or None if it could not be opened.
        The dialog is a child window of OBS (not top-level).
        """
        # Open Tools menu via menu bar, then click Teleport
        try:
            obs_win.set_focus()
            time.sleep(self._ACTION_DELAY)

            menu_bars = obs_win.children(control_type="MenuBar")
            if not menu_bars:
                return None
            mb = menu_bars[0]
            tools_item = None
            for child in mb.children():
                if child.window_text() == "Tools":
                    tools_item = child
                    break
            if tools_item is None:
                return None
            tools_item.click_input()
            time.sleep(0.8)

            # Find and click "Teleport" in the expanded menu
            for mi in obs_win.descendants(control_type="MenuItem"):
                if mi.window_text() == "Teleport":
                    mi.click_input()
                    break
            time.sleep(0.8)
        except Exception:
            return None

        # The dialog title is "Properties for 'Teleport'", class OBSBasicProperties
        deadline = time.time() + self._ELEMENT_TIMEOUT
        while time.time() < deadline:
            try:
                dlg = obs_win.child_window(
                    title="Properties for 'Teleport'",
                    class_name="OBSBasicProperties",
                )
                if dlg.exists():
                    return dlg
            except Exception:
                pass
            time.sleep(0.3)
        return None

    def _find_teleport_controls(self, dialog):
        """Map the Teleport dialog controls by descendant index.

        Returns a dict with keys: enabled_checkbox, identifier_edit, ok_button
        or None if controls could not be found.

        Dialog control map (from discovery):
          [9]  CheckBox: "Teleport Enabled"
          [13] Edit: Identifier field
          [15] UpDown: TCP Port
          [17] Slider + [18] UpDown: Quality
          OK button shifts index when warning text appears after enabling.
        """
        try:
            descendants = dialog.descendants()
        except Exception:
            return None

        controls = {}

        # Find the "Teleport Enabled" checkbox
        checkboxes = [d for d in descendants if d.element_info.control_type == "CheckBox"]
        for cb in checkboxes:
            try:
                if "Teleport" in cb.window_text() or "Enable" in cb.window_text().lower():
                    controls["enabled_checkbox"] = cb
                    break
            except Exception:
                continue

        # Find edit fields — there's typically only one (Identifier)
        edits = [d for d in descendants if d.element_info.control_type == "Edit"]
        if edits:
            controls["identifier_edit"] = edits[0]

        # Find UpDown/Spinner controls (port, quality)
        spinners = [d for d in descendants if d.element_info.control_type == "Spinner"]
        if len(spinners) >= 1:
            controls["port_spinner"] = spinners[0]
        if len(spinners) >= 2:
            controls["quality_spinner"] = spinners[1]

        # Find OK button — look for QPushButton with text "OK"
        buttons = [d for d in descendants if d.element_info.control_type == "Button"]
        for btn in buttons:
            try:
                if btn.window_text() == "OK":
                    controls["ok_button"] = btn
                    break
            except Exception:
                continue

        # Also find Cancel for cleanup
        for btn in buttons:
            try:
                if btn.window_text() == "Cancel":
                    controls["cancel_button"] = btn
                    break
            except Exception:
                continue

        return controls

    def _handle_settings_changed_dialog(self, obs_win, action: str = "save"):
        """Handle the 'Settings changed' confirmation dialog if it appears.

        OBS shows this QMessageBox when the Teleport dialog is closed
        without clicking OK (e.g. via ESC or window close).
        Buttons: Save / Discard / Cancel.

        Args:
            obs_win: The OBS main window handle.
            action: 'save' to click Save, 'discard' to click Discard.
        """
        time.sleep(0.3)
        target_text = "Save" if action == "save" else "Discard"

        # Try multiple approaches to find the dialog
        dialog = None

        # 1. As child of OBS main window
        for title in ("Settings changed", "Settings Changed"):
            try:
                candidate = obs_win.child_window(title=title)
                if candidate.exists(timeout=0.3):
                    dialog = candidate
                    break
            except Exception:
                continue

        # 2. As top-level window
        if dialog is None:
            try:
                desktop = Desktop(backend="uia")
                for title in ("Settings changed", "Settings Changed"):
                    try:
                        candidate = desktop.window(title=title)
                        if candidate.exists(timeout=0.3):
                            dialog = candidate
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        if dialog is None:
            return

        # Click the target button
        try:
            buttons = dialog.children(control_type="Button")
            for btn in buttons:
                try:
                    if btn.window_text() == target_text:
                        btn.click_input()
                        time.sleep(self._ACTION_DELAY)
                        return
                except Exception:
                    continue
        except Exception:
            pass

    def _close_teleport_dialog_safely(self, dialog, obs):
        """Close the Teleport dialog using OK/Enter. Never use ESC.

        Using ESC triggers 'Settings changed' confirmation when changes
        were made. OK/Enter saves and closes cleanly.
        """
        import pywinauto.keyboard as kb
        # Try clicking OK button first
        try:
            for desc in dialog.descendants():
                try:
                    if (desc.element_info.control_type == "Button"
                            and desc.window_text() == "OK"):
                        desc.click_input()
                        time.sleep(0.5)
                        return
                except Exception:
                    continue
        except Exception:
            pass
        # Fallback: Enter key
        try:
            kb.send_keys("{ENTER}")
            time.sleep(0.5)
        except Exception:
            pass

    def _teleport_configure_attempt(self, obs, enabled, identifier, port, quality):
        """Single attempt to configure Teleport. Returns response dict or None on transient error."""
        dialog = self._open_teleport_dialog(obs)
        if dialog is None:
            return error_response(
                ErrorCode.TELEPORT_PLUGIN_NOT_FOUND,
                "Could not open Teleport dialog. Is the Teleport plugin installed?",
            )

        # Find controls — retry a few times for COM settling
        controls = None
        for _ in range(3):
            try:
                controls = self._find_teleport_controls(dialog)
                if controls and "enabled_checkbox" in controls:
                    controls["enabled_checkbox"].get_toggle_state()
                    break
            except Exception:
                controls = None
                time.sleep(0.5)

        if controls is None or "enabled_checkbox" not in controls:
            self._close_teleport_dialog_safely(dialog, obs)
            return error_response(
                ErrorCode.TELEPORT_DIALOG_FAILED,
                "Could not locate Teleport dialog controls",
            )

        try:
            return self._apply_teleport_settings(
                dialog, controls, obs, enabled, identifier, port, quality,
            )
        except Exception:
            # COM/transient error — close dialog safely (OK, not ESC)
            # and return None to signal retry
            self._close_teleport_dialog_safely(dialog, obs)
            time.sleep(0.5)
            return None

    def _apply_teleport_settings(self, dialog, controls, obs,
                                 enabled, identifier, port, quality):
        """Apply settings to the open Teleport dialog and click OK."""
        # Toggle checkbox — state 0 = unchecked, nonzero = checked
        cb = controls["enabled_checkbox"]
        current_state = cb.get_toggle_state()
        if enabled and current_state == 0:
            cb.click_input()
            time.sleep(self._ACTION_DELAY)
        elif not enabled and current_state != 0:
            cb.click_input()
            time.sleep(self._ACTION_DELAY)

        # Set identifier
        if "identifier_edit" in controls and identifier:
            edit = controls["identifier_edit"]
            edit.click_input()
            time.sleep(0.1)
            edit.type_keys("^a", pause=0.05)
            edit.type_keys(identifier, with_spaces=True, pause=0.02)
            time.sleep(self._ACTION_DELAY)

        # Set port via spinner (best-effort)
        if "port_spinner" in controls:
            try:
                spinner = controls["port_spinner"]
                spinner.click_input()
                time.sleep(0.1)
                spinner.type_keys("^a", pause=0.05)
                spinner.type_keys(str(port), pause=0.02)
                time.sleep(self._ACTION_DELAY)
            except Exception:
                pass

        # Set quality via spinner (best-effort, skip if default)
        if "quality_spinner" in controls and quality != 90:
            try:
                spinner = controls["quality_spinner"]
                spinner.click_input()
                time.sleep(0.1)
                spinner.type_keys("^a", pause=0.05)
                spinner.type_keys(str(quality), pause=0.02)
                time.sleep(self._ACTION_DELAY)
            except Exception:
                pass

        # Click OK — always use fresh descendants scan since checkbox
        # toggle adds a warning label that shifts button indices
        self._close_teleport_dialog_safely(dialog, obs)

        return success_response({
            "teleport_enabled": enabled,
            "identifier": identifier,
            "port": port,
            "quality": quality,
            "configured": True,
        })

    # ------------------------------------------------------------------
    # Public API: Teleport plugin
    # ------------------------------------------------------------------

    def teleport_configure_host(
        self,
        enabled: bool = True,
        identifier: str = "OBSTeleport",
        port: int = 0,
        quality: int = 90,
    ) -> dict[str, Any]:
        """Configure the Teleport output on the host machine.

        Opens Tools -> Teleport dialog, sets enabled state, identifier,
        port, and quality, then clicks OK.
        Retries the entire operation up to 3 times to handle transient
        COM/UIA errors that occur when OBS dialogs are still settling.
        """
        if not 0 <= port <= 65535:
            return error_response(ErrorCode.INVALID_PARAMETER, f"port must be 0-65535, got {port}")
        if not 1 <= quality <= 100:
            return error_response(ErrorCode.INVALID_PARAMETER, f"quality must be 1-100, got {quality}")

        with self._lock:
            obs = self._find_obs_window()
            if obs is None:
                return error_response(ErrorCode.OBS_NOT_CONNECTED, "OBS Studio window not found")

            last_error = ""
            for attempt in range(3):
                if attempt > 0:
                    time.sleep(1.0)

                result = self._teleport_configure_attempt(
                    obs, enabled, identifier, port, quality,
                )
                if result is not None:
                    return result
                last_error = f"Attempt {attempt + 1} hit transient COM error"

            return error_response(
                ErrorCode.TELEPORT_DIALOG_FAILED,
                f"Failed to configure Teleport after 3 attempts: {last_error}",
            )
