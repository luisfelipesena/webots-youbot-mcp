"""
MCP Bridge for Webots Controllers.

A lightweight, generic bridge between ANY Webots controller and the MCP server.
Minimal API - just call publish() with your state dict.

Usage:
    from mcp_bridge import MCPBridge

    bridge = MCPBridge(robot)

    # In main loop - just pass a dict with whatever state you want to expose:
    bridge.publish({
        "pose": [x, y, theta],
        "mode": "search",
        "collected": 5,
        # ... any other fields
    })

    # Optionally check for commands:
    cmd = bridge.get_command()
    if cmd:
        handle_command(cmd)
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional


# Default data directory (sibling to this file)
DEFAULT_DATA_DIR = Path(__file__).parent / "data"


class MCPBridge:
    """Minimal bridge between Webots controller and MCP server."""

    def __init__(self, robot, data_dir: Optional[Path] = None):
        """
        Initialize MCP bridge.

        Args:
            robot: Webots Robot/Supervisor instance
            data_dir: Path to data directory (default: ./data)
        """
        self.robot = robot
        self._is_supervisor = hasattr(robot, 'simulationSetMode')
        self.data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR

        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "camera").mkdir(exist_ok=True)
        (self.data_dir / "screenshots").mkdir(exist_ok=True)
        (self.data_dir / "logs").mkdir(exist_ok=True)

        # Files
        self.status_file = self.data_dir / "status.json"
        self.commands_file = self.data_dir / "commands.json"
        self.log_file = self.data_dir / "logs" / "controller.log"

        # State
        self._last_cmd_ts = None
        self._update_counter = 0
        self._update_interval = 5  # Write every N calls to reduce I/O

    def publish(self, state: Dict[str, Any]):
        """
        Publish robot state to MCP server.

        Call this every timestep with your current state.
        The bridge handles throttling automatically.

        Args:
            state: Dict with any fields (pose, mode, sensors, etc.)
        """
        self._update_counter += 1
        if self._update_counter % self._update_interval != 0:
            return

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
            Command dict if new command available, None otherwise.
            Handles the command internally if it's a simulation control.
        """
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

        # Handle built-in commands
        action = cmd.get("action")
        if action == "simulation":
            self._handle_simulation_cmd(cmd)
        elif action == "screenshot":
            self._handle_screenshot_cmd(cmd)

        return cmd

    def _handle_simulation_cmd(self, cmd: Dict[str, Any]):
        """Handle simulation control commands."""
        if not self._is_supervisor:
            return

        command = cmd.get("command")
        try:
            if command == "pause":
                self.robot.simulationSetMode(self.robot.SIMULATION_MODE_PAUSE)
            elif command == "resume":
                self.robot.simulationSetMode(self.robot.SIMULATION_MODE_REAL_TIME)
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
            max_frames: Max frames to keep
        """
        try:
            image = camera.getImage()
            if not image:
                return

            from PIL import Image
            w, h = camera.getWidth(), camera.getHeight()
            img = Image.frombytes('RGBA', (w, h), image).convert('RGB')

            # Rolling filename
            frame_num = self._update_counter % max_frames
            path = self.data_dir / "camera" / f"frame_{frame_num:04d}.png"
            img.save(path)
        except ImportError:
            pass  # PIL not available
        except Exception:
            pass
