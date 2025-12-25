"""
MCP Bridge for Webots Controllers.

Generic, minimal bridge between ANY Webots controller and Claude Code via MCP.
Requires only 3 lines of code in your controller.

Usage:
    from mcp_bridge import MCPBridge

    bridge = MCPBridge(robot)  # Auto-detects Supervisor
    bridge.publish({"pose": [x, y, theta], "mode": "navigate"})

Advanced:
    bridge.on_reload(reset_callback)  # Auto-detect world reloads
    bridge.register_command("custom_action", handler_fn)
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Callable, List


class MCPBridge:
    """Minimal bridge between Webots controller and MCP server."""

    def __init__(
        self,
        robot,
        data_dir: Optional[Path] = None,
        throttle_interval: int = 5,
    ):
        """
        Initialize MCP bridge.

        Args:
            robot: Webots Robot or Supervisor instance
            data_dir: Path to data directory (default: auto-detect)
            throttle_interval: Publish every N calls (reduces I/O)
        """
        self.robot = robot
        self._is_supervisor = hasattr(robot, 'simulationSetMode')

        # Auto-detect data directory
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            # Try common locations
            candidates = [
                Path(__file__).parent / "data",
                Path.cwd() / "mcp_data",
                Path.home() / ".webots-mcp" / "data",
            ]
            self.data_dir = next((p for p in candidates if p.exists()), candidates[0])

        # Lazy initialization flag
        self._initialized = False

        # Throttling
        self._update_counter = 0
        self._throttle_interval = throttle_interval

        # Command handlers
        self._command_handlers: Dict[str, Callable] = {}
        self._last_cmd_ts = None

        # Reload detection
        self._sim_time = 0.0
        self._reload_callback: Optional[Callable] = None

        # Files (set on first use)
        self.status_file: Optional[Path] = None
        self.commands_file: Optional[Path] = None
        self.log_file: Optional[Path] = None

    def _ensure_dirs(self):
        """Create directories on first use (lazy init)."""
        if self._initialized:
            return

        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "camera").mkdir(exist_ok=True)
        (self.data_dir / "screenshots").mkdir(exist_ok=True)
        (self.data_dir / "logs").mkdir(exist_ok=True)

        self.status_file = self.data_dir / "status.json"
        self.commands_file = self.data_dir / "commands.json"
        self.log_file = self.data_dir / "logs" / "controller.log"

        self._initialized = True

    def publish(self, state: Dict[str, Any], force: bool = False):
        """
        Publish robot state to MCP server.

        Call every timestep with your current state dict.
        Throttled automatically to reduce I/O.

        Args:
            state: Dict with any fields (pose, mode, sensors, etc.)
            force: Bypass throttling and publish immediately
        """
        self._update_counter += 1
        if not force and self._update_counter % self._throttle_interval != 0:
            return

        self._ensure_dirs()

        # Add timestamp
        state["timestamp"] = datetime.now().isoformat()

        try:
            with open(self.status_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    def get_command(self) -> Optional[Dict[str, Any]]:
        """
        Check for commands from MCP server.

        Returns:
            Command dict if new command, None otherwise.
            Built-in commands (simulation, screenshot) handled automatically.
        """
        self._ensure_dirs()

        if not self.commands_file.exists():
            return None

        try:
            with open(self.commands_file, 'r') as f:
                cmd = json.load(f)
        except Exception:
            return None

        # Check if new command
        ts = cmd.get("timestamp")
        if ts == self._last_cmd_ts:
            return None
        self._last_cmd_ts = ts

        # CRITICAL: Clear the command file BEFORE processing to prevent reload loops
        # When worldReload() is called, the controller restarts and would re-read the same command
        self._clear_command_file()

        # Handle built-in commands
        action = cmd.get("action")
        if action == "simulation":
            self._handle_simulation_cmd(cmd)
        elif action == "screenshot":
            self._handle_screenshot_cmd(cmd)
        elif action in self._command_handlers:
            self._command_handlers[action](cmd)

        return cmd

    def register_command(self, action: str, handler: Callable[[Dict], None]):
        """
        Register custom command handler.

        Args:
            action: Command action name (e.g., "custom_reset")
            handler: Function(cmd_dict) to handle command
        """
        self._command_handlers[action] = handler

    def on_reload(self, callback: Callable[[], None]):
        """
        Register callback for world reload detection.

        Args:
            callback: Function() called when world reload is detected
        """
        self._reload_callback = callback

    def detect_reload(self) -> bool:
        """
        Detect if world was reloaded (simulation time jumped backwards).

        Returns:
            True if reload detected
        """
        try:
            current = self.robot.getTime()
        except Exception:
            return False

        if current < self._sim_time - 0.1:  # Small tolerance
            if self._reload_callback:
                self.log("World reload detected - calling reset callback")
                self._reload_callback()
            self._sim_time = 0.0
            return True

        self._sim_time = current
        return False

    def _clear_command_file(self):
        """Clear the command file to prevent reload loops."""
        try:
            with open(self.commands_file, 'w') as f:
                json.dump({"action": "none", "command": "cleared", "timestamp": "0"}, f)
        except Exception:
            pass

    def _handle_simulation_cmd(self, cmd: Dict[str, Any]):
        """Handle simulation control commands."""
        if not self._is_supervisor:
            self.log("Warning: simulation control requires Supervisor")
            return

        command = cmd.get("command")
        try:
            if command == "pause":
                self.robot.simulationSetMode(self.robot.SIMULATION_MODE_PAUSE)
            elif command == "resume":
                self.robot.simulationSetMode(self.robot.SIMULATION_MODE_REAL_TIME)
            elif command == "fast":
                self.robot.simulationSetMode(self.robot.SIMULATION_MODE_FAST)
            elif command == "reset":
                self.robot.simulationReset()
            elif command == "reload":
                self.robot.worldReload()
            elif command == "step":
                self.robot.step(int(self.robot.getBasicTimeStep()))
            self.log(f"Simulation: {command}")
        except Exception as e:
            self.log(f"Simulation control error: {e}")

    def _handle_screenshot_cmd(self, cmd: Dict[str, Any]):
        """Handle screenshot command."""
        if not self._is_supervisor:
            return

        filename = cmd.get("filename", f"screenshot_{datetime.now().strftime('%H%M%S')}")
        path = self.data_dir / "screenshots" / f"{filename}.png"

        try:
            self.robot.exportImage(str(path), 100)
            self.log(f"Screenshot: {path.name}")
        except Exception as e:
            self.log(f"Screenshot error: {e}")

    def log(self, message: str):
        """Append message to log file."""
        self._ensure_dirs()
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            with open(self.log_file, 'a') as f:
                f.write(f"[{ts}] {message}\n")
        except Exception:
            pass

    def save_camera_frame(self, camera, max_frames: int = 50):
        """
        Save camera frame to file.

        Args:
            camera: Webots Camera device
            max_frames: Max frames to keep (rolling)
        """
        self._ensure_dirs()
        try:
            image = camera.getImage()
            if not image:
                return

            from PIL import Image
            w, h = camera.getWidth(), camera.getHeight()
            img = Image.frombytes('RGBA', (w, h), image).convert('RGB')

            frame_num = self._update_counter % max_frames
            path = self.data_dir / "camera" / f"frame_{frame_num:04d}.png"
            img.save(path)
        except ImportError:
            pass  # PIL not available
        except Exception:
            pass

    # === Convenience Methods ===

    def auto_publish(
        self,
        extra: Optional[Dict] = None,
        include_time: bool = True,
    ) -> Dict[str, Any]:
        """
        Auto-extract and publish common robot data.

        Args:
            extra: Additional fields to merge
            include_time: Include simulation time

        Returns:
            Published state dict
        """
        state = extra or {}

        if include_time:
            try:
                state["sim_time"] = self.robot.getTime()
            except Exception:
                pass

        self.publish(state)
        return state
