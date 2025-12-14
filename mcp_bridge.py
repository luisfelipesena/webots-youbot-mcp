"""
MCP Bridge for YouBot Controller.

This module provides the integration layer between the YouBot controller
and the MCP server. It handles:
- Writing robot status to status.json
- Reading commands from commands.json
- Saving camera frames
- Generating occupancy grid visualizations
- Logging controller output

Usage:
    from mcp_bridge import MCPBridge

    bridge = MCPBridge(robot, data_dir="/path/to/webots-youbot-mcp/data")

    # In main loop:
    bridge.update_status(controller_state)
    bridge.process_commands()
"""

import json
import os
import math
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple


class MCPBridge:
    """Bridge between YouBot controller and MCP server."""

    def __init__(self, robot, data_dir: Optional[str] = None):
        """
        Initialize MCP bridge.

        Args:
            robot: Webots Robot/Supervisor instance
            data_dir: Path to MCP data directory (default: auto-detect)
        """
        self.robot = robot
        self._is_supervisor = hasattr(robot, 'getSelf')

        # Find data directory
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            # Try to find webots-youbot-mcp relative to project
            project_root = Path(__file__).parent.parent
            self.data_dir = project_root / "webots-youbot-mcp" / "data"

        # Ensure directories exist
        self.status_file = self.data_dir / "status.json"
        self.commands_file = self.data_dir / "commands.json"
        self.camera_dir = self.data_dir / "camera"
        self.screenshots_dir = self.data_dir / "screenshots"
        self.logs_dir = self.data_dir / "logs"
        self.grid_dir = self.data_dir / "grid"

        for d in [self.data_dir, self.camera_dir, self.screenshots_dir,
                  self.logs_dir, self.grid_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Log file
        self.log_file = self.logs_dir / "controller.log"
        self._setup_logging()

        # State
        self._last_command_timestamp = None
        self._frame_counter = 0
        self._status_update_interval = 5  # Update every N steps
        self._step_counter = 0

    def _setup_logging(self):
        """Setup logging to file and console."""
        # We'll capture prints by also writing to log file
        pass

    def log(self, message: str, level: str = "INFO"):
        """Write log message to file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] [{level}] {message}\n"
        try:
            with open(self.log_file, 'a') as f:
                f.write(line)
        except Exception:
            pass

    def update_status(
        self,
        pose: List[float],
        mode: str,
        collected: int,
        max_cubes: int = 15,
        current_target: Optional[str] = None,
        delivered: Optional[Dict[str, int]] = None,
        lidar_data: Optional[Dict[str, Any]] = None,
        distance_sensors: Optional[Dict[str, float]] = None,
        recognized_objects: Optional[List[Dict]] = None,
        waypoints: Optional[List[Tuple[float, float]]] = None,
        current_waypoint_index: int = 0,
        active_goal: Optional[Tuple[float, float]] = None,
        arm_state: Optional[Dict[str, float]] = None,
        gripper_state: Optional[Dict[str, Any]] = None,
        grid_ascii: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None
    ):
        """
        Update robot status for MCP server.

        Args:
            pose: [x, y, yaw] robot position
            mode: Current operating mode
            collected: Number of cubes collected
            max_cubes: Total cubes to collect
            current_target: Current target (e.g., "red", "blue", "green")
            delivered: Dict of cubes delivered per color
            lidar_data: LIDAR sensor readings
            distance_sensors: Distance sensor readings
            recognized_objects: List of detected objects
            waypoints: Current path waypoints
            current_waypoint_index: Index in waypoints
            active_goal: Current navigation goal
            arm_state: Arm joint positions
            gripper_state: Gripper state info
            grid_ascii: ASCII visualization of occupancy grid
            extra: Additional data to include
        """
        self._step_counter += 1

        # Only update every N steps to reduce I/O
        if self._step_counter % self._status_update_interval != 0:
            return

        status = {
            "timestamp": datetime.now().isoformat(),
            "pose": pose if pose else [0, 0, 0],
            "mode": mode,
            "collected": collected,
            "max_cubes": max_cubes,
            "current_target": current_target,
            "delivered": delivered or {"red": 0, "green": 0, "blue": 0},
        }

        if lidar_data:
            status["lidar"] = lidar_data

        if distance_sensors:
            status["distance_sensors"] = distance_sensors

        if recognized_objects:
            status["recognized_objects"] = recognized_objects

        if waypoints:
            status["waypoints"] = [[w[0], w[1]] for w in waypoints]
            status["current_waypoint_index"] = current_waypoint_index

        if active_goal:
            status["active_goal"] = [active_goal[0], active_goal[1]]

        if arm_state:
            status["arm"] = arm_state

        if gripper_state:
            status["gripper"] = gripper_state

        if grid_ascii:
            status["grid_ascii"] = grid_ascii
            # Also save to file
            try:
                (self.grid_dir / "grid.txt").write_text(grid_ascii)
            except Exception:
                pass

        if extra:
            status.update(extra)

        # Write to status file
        try:
            with open(self.status_file, 'w') as f:
                json.dump(status, f, indent=2)
        except Exception as e:
            self.log(f"Failed to write status: {e}", "ERROR")

    def process_commands(self) -> Optional[Dict[str, Any]]:
        """
        Check for and process commands from MCP server.

        Returns:
            Command dict if new command available, None otherwise
        """
        if not self.commands_file.exists():
            return None

        try:
            with open(self.commands_file, 'r') as f:
                cmd = json.load(f)
        except (json.JSONDecodeError, Exception):
            return None

        # Check if this is a new command
        timestamp = cmd.get("timestamp")
        if timestamp == self._last_command_timestamp:
            return None

        self._last_command_timestamp = timestamp
        action = cmd.get("action")

        if action == "screenshot":
            self._handle_screenshot(cmd)
        elif action == "simulation_control":
            self._handle_simulation_control(cmd)

        return cmd

    def _handle_screenshot(self, cmd: Dict[str, Any]):
        """Handle screenshot command."""
        if not self._is_supervisor:
            self.log("Cannot take screenshot: not running as supervisor", "WARN")
            return

        filename = cmd.get("filename", f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        filepath = self.screenshots_dir / f"{filename}.png"

        try:
            # Webots supervisor screenshot
            self.robot.exportImage(str(filepath), 100)
            self.log(f"Screenshot saved: {filepath}")
        except Exception as e:
            self.log(f"Screenshot failed: {e}", "ERROR")

    def _handle_simulation_control(self, cmd: Dict[str, Any]):
        """Handle simulation control command."""
        if not self._is_supervisor:
            self.log("Cannot control simulation: not running as supervisor", "WARN")
            return

        command = cmd.get("command")

        try:
            if command == "pause":
                self.robot.simulationSetMode(self.robot.SIMULATION_MODE_PAUSE)
                self.log("Simulation paused")
            elif command == "resume":
                self.robot.simulationSetMode(self.robot.SIMULATION_MODE_REAL_TIME)
                self.log("Simulation resumed")
            elif command == "reset":
                self.robot.simulationReset()
                self.log("Simulation reset")
            elif command == "step":
                self.robot.step(int(self.robot.getBasicTimeStep()))
                self.log("Single step executed")
        except Exception as e:
            self.log(f"Simulation control failed: {e}", "ERROR")

    def save_camera_frame(self, camera, max_frames: int = 100):
        """
        Save current camera frame to file.

        Args:
            camera: Webots Camera device
            max_frames: Maximum frames to keep (oldest deleted)
        """
        try:
            # Get image data
            image = camera.getImage()
            if not image:
                return

            width = camera.getWidth()
            height = camera.getHeight()

            # Save as PNG using PIL
            try:
                from PIL import Image
                # Webots returns BGRA
                img = Image.frombytes('RGBA', (width, height), image)
                # Convert BGRA to RGB
                img = img.convert('RGB')

                self._frame_counter += 1
                filename = f"frame_{self._frame_counter:06d}.png"
                filepath = self.camera_dir / filename

                img.save(filepath)

                # Cleanup old frames
                self._cleanup_old_frames(max_frames)

            except ImportError:
                # Fallback: save raw bytes
                self._frame_counter += 1
                filename = f"frame_{self._frame_counter:06d}.raw"
                filepath = self.camera_dir / filename
                with open(filepath, 'wb') as f:
                    f.write(image)

        except Exception as e:
            self.log(f"Failed to save camera frame: {e}", "ERROR")

    def _cleanup_old_frames(self, max_frames: int):
        """Remove old camera frames beyond max_frames."""
        frames = sorted(self.camera_dir.glob("frame_*.png"))
        if len(frames) > max_frames:
            for f in frames[:-max_frames]:
                try:
                    f.unlink()
                except Exception:
                    pass

    def generate_grid_ascii(
        self,
        grid,
        robot_pos: Tuple[float, float],
        scale: int = 3
    ) -> str:
        """
        Generate ASCII representation of occupancy grid.

        Args:
            grid: OccupancyGrid instance
            robot_pos: (x, y) robot position
            scale: Cells to skip (1 = full resolution)

        Returns:
            ASCII string visualization
        """
        lines = []

        # Get robot cell
        robot_cell = grid.world_to_cell(robot_pos[0], robot_pos[1])

        for gy in range(grid.height - 1, -1, -scale):  # Top to bottom
            row = ""
            for gx in range(0, grid.width, scale):
                if robot_cell and gx == robot_cell[0] and gy == robot_cell[1]:
                    row += "R"
                else:
                    val = grid.get(gx, gy)
                    if val == grid.OBSTACLE:
                        row += "#"
                    elif val == grid.FREE:
                        row += "."
                    elif val == grid.BOX:
                        row += "B"
                    elif val == grid.CUBE:
                        row += "C"
                    else:
                        row += "?"
            lines.append(row)

        return "\n".join(lines)

    def collect_lidar_data(
        self,
        lidars: Dict[str, Any],
        max_points_per_lidar: int = 20
    ) -> Dict[str, Any]:
        """
        Collect and summarize LIDAR data.

        Args:
            lidars: Dict of {name: lidar_device}
            max_points_per_lidar: Max points to store per LIDAR

        Returns:
            Summary dict with min distances and obstacle info
        """
        result = {
            "min_distances": {},
            "obstacle_count": 0
        }

        for name, lidar in lidars.items():
            try:
                ranges = lidar.getRangeImage()
                if ranges:
                    valid_ranges = [r for r in ranges if r < lidar.getMaxRange()]
                    if valid_ranges:
                        result["min_distances"][name] = min(valid_ranges)
                        result["obstacle_count"] += len([r for r in valid_ranges if r < 1.0])
                    else:
                        result["min_distances"][name] = float('inf')
            except Exception:
                pass

        return result

    def collect_distance_sensors(self, sensors: Dict[str, Any]) -> Dict[str, float]:
        """
        Collect distance sensor readings.

        Args:
            sensors: Dict of {name: sensor_device}

        Returns:
            Dict of {name: value}
        """
        result = {}
        for name, sensor in sensors.items():
            try:
                result[name] = sensor.getValue()
            except Exception:
                pass
        return result

    def collect_recognized_objects(self, camera) -> List[Dict[str, Any]]:
        """
        Collect recognized objects from camera.

        Args:
            camera: Webots Camera with recognition enabled

        Returns:
            List of recognized objects with color, distance, angle
        """
        objects = []
        try:
            recognized = camera.getRecognitionObjects()
            for obj in recognized:
                color_arr = obj.getColors()
                # Determine color from RGB
                if color_arr[0] > 0.5 and color_arr[1] < 0.5:
                    color = "red"
                elif color_arr[1] > 0.5 and color_arr[0] < 0.5:
                    color = "green"
                elif color_arr[2] > 0.5:
                    color = "blue"
                else:
                    color = "unknown"

                pos = obj.getPosition()
                distance = math.sqrt(pos[0]**2 + pos[1]**2 + pos[2]**2)
                angle = math.degrees(math.atan2(pos[1], pos[0]))

                objects.append({
                    "color": color,
                    "distance": round(distance, 3),
                    "angle": round(angle, 1)
                })
        except Exception:
            pass

        return objects
