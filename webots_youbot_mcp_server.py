#!/usr/bin/env python3
"""
MCP Server for Webots YouBot Simulation.

Provides tools for Claude Code to monitor and analyze the YouBot robot
in a Webots simulation, including sensor data, camera images, screenshots,
task progress, and simulation control.
"""

import json
import os
import base64
import glob
from pathlib import Path
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("webots_youbot_mcp")

# Constants
CHARACTER_LIMIT = 25000
DATA_DIR = Path(__file__).parent / "data"
STATUS_FILE = DATA_DIR / "status.json"
COMMANDS_FILE = DATA_DIR / "commands.json"
CAMERA_DIR = DATA_DIR / "camera"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
LOGS_DIR = DATA_DIR / "logs"
GRID_DIR = DATA_DIR / "grid"

# Ensure directories exist
for d in [DATA_DIR, CAMERA_DIR, SCREENSHOTS_DIR, LOGS_DIR, GRID_DIR]:
    d.mkdir(parents=True, exist_ok=True)


class ResponseFormat(str, Enum):
    """Output format for tool responses."""
    MARKDOWN = "markdown"
    JSON = "json"


# ============== Input Models ==============

class EmptyInput(BaseModel):
    """Input model for tools with no parameters."""
    model_config = ConfigDict(extra='forbid')


class ResponseFormatInput(BaseModel):
    """Input with optional response format."""
    model_config = ConfigDict(extra='forbid')
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for machine-readable"
    )


class LogsInput(BaseModel):
    """Input for log retrieval."""
    model_config = ConfigDict(extra='forbid')
    lines: int = Field(default=50, description="Number of log lines to retrieve", ge=1, le=500)
    filter_text: Optional[str] = Field(default=None, description="Filter logs containing this text")


class ScreenshotInput(BaseModel):
    """Input for screenshot operations."""
    model_config = ConfigDict(extra='forbid')
    save_path: Optional[str] = Field(default=None, description="Custom filename (without extension)")


class SimulationCommandInput(BaseModel):
    """Input for simulation control commands."""
    model_config = ConfigDict(extra='forbid')
    command: str = Field(
        ...,
        description="Command: 'pause', 'resume', 'reset', 'step'",
        pattern="^(pause|resume|reset|step)$"
    )


# ============== Helper Functions ==============

def _load_status() -> Dict[str, Any]:
    """Load current robot status from JSON file."""
    if not STATUS_FILE.exists():
        return {"error": "No status file found. Is the simulation running?"}
    try:
        with open(STATUS_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {"error": "Status file is corrupted or being written"}


def _write_command(cmd: Dict[str, Any]) -> bool:
    """Write command to commands.json for the controller to process."""
    try:
        cmd["timestamp"] = datetime.now().isoformat()
        with open(COMMANDS_FILE, 'w') as f:
            json.dump(cmd, f, indent=2)
        return True
    except Exception:
        return False


def _format_pose(pose: List[float]) -> str:
    """Format pose as readable string."""
    if not pose or len(pose) < 3:
        return "Unknown"
    import math
    x, y, yaw = pose[0], pose[1], pose[2]
    yaw_deg = math.degrees(yaw)
    return f"({x:.2f}, {y:.2f}) θ={yaw_deg:.1f}°"


def _get_latest_image(directory: Path, pattern: str = "*.png") -> Optional[Path]:
    """Get the most recent image from a directory."""
    files = list(directory.glob(pattern))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


# ============== Tools ==============

@mcp.tool(
    name="webots_get_robot_status",
    annotations={
        "title": "Get Robot Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def webots_get_robot_status(params: ResponseFormatInput) -> str:
    """
    Get current YouBot robot status including position, mode, and task progress.

    Returns robot pose (x, y, θ), current operating mode (search/approach/pick/deliver),
    number of cubes collected, current target, and timing information.

    Args:
        params: Response format options

    Returns:
        Robot status in requested format (markdown or JSON)

    Example:
        - Use when: "Where is the robot now?"
        - Use when: "What is the robot doing?"
        - Use when: "How many cubes collected?"
    """
    status = _load_status()

    if "error" in status:
        return f"Error: {status['error']}"

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(status, indent=2)

    # Markdown format
    lines = ["# YouBot Status", ""]

    # Pose
    pose = status.get("pose", [])
    lines.append(f"**Position**: {_format_pose(pose)}")

    # Mode
    mode = status.get("mode", "unknown")
    lines.append(f"**Mode**: `{mode}`")

    # Task progress
    collected = status.get("collected", 0)
    max_cubes = status.get("max_cubes", 15)
    lines.append(f"**Cubes Collected**: {collected}/{max_cubes}")

    # Current target
    target = status.get("current_target")
    if target:
        lines.append(f"**Current Target**: {target}")

    # Delivery stats
    delivered = status.get("delivered", {})
    if delivered:
        lines.append("")
        lines.append("## Delivery Stats")
        for color, count in delivered.items():
            lines.append(f"- **{color.upper()}**: {count}")

    # Timestamp
    ts = status.get("timestamp")
    if ts:
        lines.append("")
        lines.append(f"*Updated: {ts}*")

    return "\n".join(lines)


@mcp.tool(
    name="webots_get_lidar_readings",
    annotations={
        "title": "Get LIDAR Readings",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def webots_get_lidar_readings(params: ResponseFormatInput) -> str:
    """
    Get all LIDAR sensor readings from the YouBot's 4 LIDAR sensors.

    The YouBot has 4 LIDARs: front (180°), rear (180°), left (180°), right (180°).
    Returns minimum distances detected in each direction and obstacle warnings.

    Args:
        params: Response format options

    Returns:
        LIDAR data with minimum distances per direction

    Example:
        - Use when: "Is there something in front of the robot?"
        - Use when: "What obstacles are nearby?"
    """
    status = _load_status()

    if "error" in status:
        return f"Error: {status['error']}"

    lidar = status.get("lidar", {})
    if not lidar:
        return "No LIDAR data available"

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(lidar, indent=2)

    # Markdown format
    lines = ["# LIDAR Readings", ""]

    min_distances = lidar.get("min_distances", {})

    # Direction indicators
    directions = {
        "front": "⬆️ FRONT",
        "rear": "⬇️ REAR",
        "left": "⬅️ LEFT",
        "right": "➡️ RIGHT"
    }

    for key, label in directions.items():
        dist = min_distances.get(key, float('inf'))
        if dist < 0.3:
            status_icon = "🔴 DANGER"
        elif dist < 0.6:
            status_icon = "🟡 WARNING"
        else:
            status_icon = "🟢 CLEAR"
        lines.append(f"**{label}**: {dist:.2f}m {status_icon}")

    # Obstacle count
    obstacle_count = lidar.get("obstacle_count", 0)
    lines.append("")
    lines.append(f"**Total obstacles detected**: {obstacle_count}")

    return "\n".join(lines)


@mcp.tool(
    name="webots_get_distance_sensors",
    annotations={
        "title": "Get Distance Sensors",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def webots_get_distance_sensors(params: ResponseFormatInput) -> str:
    """
    Get readings from all 8 infrared distance sensors on the YouBot.

    Sensors: ds_front, ds_rear, ds_left, ds_right, ds_front_left,
    ds_front_right, ds_rear_left, ds_rear_right

    Args:
        params: Response format options

    Returns:
        All distance sensor readings with collision warnings
    """
    status = _load_status()

    if "error" in status:
        return f"Error: {status['error']}"

    sensors = status.get("distance_sensors", {})
    if not sensors:
        return "No distance sensor data available"

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(sensors, indent=2)

    lines = ["# Distance Sensors (IR)", ""]

    for name, value in sorted(sensors.items()):
        # Convert raw value to approximate distance (lookup table dependent)
        if value < 50:
            status_icon = "🔴"
        elif value < 200:
            status_icon = "🟡"
        else:
            status_icon = "🟢"
        lines.append(f"- **{name}**: {value:.0f} {status_icon}")

    return "\n".join(lines)


@mcp.tool(
    name="webots_get_camera_image",
    annotations={
        "title": "Get Camera Image",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def webots_get_camera_image(params: EmptyInput) -> str:
    """
    Get the latest camera image captured by the YouBot.

    Returns the path to the most recent camera frame saved by the controller.
    The camera is 128x128 RGB with object recognition enabled.

    Returns:
        Path to the latest camera image file

    Example:
        - Use when: "Show me what the robot sees"
        - Use when: "What's in front of the camera?"
    """
    latest = _get_latest_image(CAMERA_DIR)

    if not latest:
        return "No camera images available. Ensure the simulation is running and saving frames."

    # Return file info
    stat = latest.stat()
    age_seconds = (datetime.now().timestamp() - stat.st_mtime)

    lines = [
        "# Latest Camera Frame",
        "",
        f"**File**: `{latest.name}`",
        f"**Path**: `{latest}`",
        f"**Age**: {age_seconds:.1f} seconds ago",
        f"**Size**: {stat.st_size} bytes",
        "",
        "Use the Read tool to view this image."
    ]

    return "\n".join(lines)


@mcp.tool(
    name="webots_get_recognized_objects",
    annotations={
        "title": "Get Recognized Objects",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def webots_get_recognized_objects(params: ResponseFormatInput) -> str:
    """
    Get list of objects detected by the camera's recognition system.

    Returns colored cubes detected with their relative position (distance, angle)
    and color classification.

    Args:
        params: Response format options

    Returns:
        List of recognized objects with position and color

    Example:
        - Use when: "Does the robot see any cubes?"
        - Use when: "What colors are detected?"
    """
    status = _load_status()

    if "error" in status:
        return f"Error: {status['error']}"

    objects = status.get("recognized_objects", [])

    if params.response_format == ResponseFormat.JSON:
        return json.dumps({"objects": objects, "count": len(objects)}, indent=2)

    if not objects:
        return "No objects currently recognized by camera."

    lines = ["# Recognized Objects", "", f"**Total**: {len(objects)} objects", ""]

    for i, obj in enumerate(objects, 1):
        color = obj.get("color", "unknown")
        distance = obj.get("distance", 0)
        angle = obj.get("angle", 0)

        color_emoji = {"red": "🔴", "green": "🟢", "blue": "🔵"}.get(color, "⚪")
        lines.append(f"{i}. {color_emoji} **{color.upper()}** - {distance:.2f}m @ {angle:.1f}°")

    return "\n".join(lines)


@mcp.tool(
    name="webots_get_occupancy_grid",
    annotations={
        "title": "Get Occupancy Grid",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def webots_get_occupancy_grid(params: EmptyInput) -> str:
    """
    Get the robot's internal occupancy grid map as ASCII visualization.

    Shows the mapped environment with obstacles, free space, and robot position.
    Legend: # = obstacle, . = free, ? = unknown, R = robot, G/B/R = boxes

    Returns:
        ASCII representation of the occupancy grid

    Example:
        - Use when: "Show me the map"
        - Use when: "What has the robot explored?"
    """
    status = _load_status()

    if "error" in status:
        return f"Error: {status['error']}"

    grid_ascii = status.get("grid_ascii")

    if not grid_ascii:
        # Try loading from file
        grid_file = GRID_DIR / "grid.txt"
        if grid_file.exists():
            grid_ascii = grid_file.read_text()
        else:
            return "No occupancy grid data available."

    lines = [
        "# Occupancy Grid",
        "",
        "```",
        grid_ascii,
        "```",
        "",
        "**Legend**: `#`=obstacle, `.`=free, `?`=unknown, `R`=robot, `G`/`B`/`D`=deposit boxes"
    ]

    return "\n".join(lines)


@mcp.tool(
    name="webots_get_current_path",
    annotations={
        "title": "Get Current Path",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def webots_get_current_path(params: ResponseFormatInput) -> str:
    """
    Get the robot's current planned navigation path (waypoints).

    Shows the sequence of waypoints the robot is following to reach its goal.

    Args:
        params: Response format options

    Returns:
        List of waypoints with current progress
    """
    status = _load_status()

    if "error" in status:
        return f"Error: {status['error']}"

    waypoints = status.get("waypoints", [])
    current_wp = status.get("current_waypoint_index", 0)
    goal = status.get("active_goal")

    if params.response_format == ResponseFormat.JSON:
        return json.dumps({
            "waypoints": waypoints,
            "current_index": current_wp,
            "goal": goal,
            "total": len(waypoints)
        }, indent=2)

    lines = ["# Navigation Path", ""]

    if goal:
        lines.append(f"**Goal**: ({goal[0]:.2f}, {goal[1]:.2f})")

    if not waypoints:
        lines.append("No active path - robot may be searching or idle.")
        return "\n".join(lines)

    lines.append(f"**Waypoints**: {len(waypoints)}")
    lines.append(f"**Progress**: {current_wp + 1}/{len(waypoints)}")
    lines.append("")

    for i, wp in enumerate(waypoints[:10]):  # Limit to 10 waypoints
        marker = "→" if i == current_wp else " "
        lines.append(f"{marker} {i+1}. ({wp[0]:.2f}, {wp[1]:.2f})")

    if len(waypoints) > 10:
        lines.append(f"  ... and {len(waypoints) - 10} more")

    return "\n".join(lines)


@mcp.tool(
    name="webots_get_task_progress",
    annotations={
        "title": "Get Task Progress",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def webots_get_task_progress(params: ResponseFormatInput) -> str:
    """
    Get detailed progress on the cube collection task.

    Shows total cubes collected, cubes delivered by color, and completion percentage.
    The task is to collect 15 cubes and sort them into colored boxes.

    Args:
        params: Response format options

    Returns:
        Detailed task progress report

    Example:
        - Use when: "How is the task going?"
        - Use when: "Did the robot finish?"
    """
    status = _load_status()

    if "error" in status:
        return f"Error: {status['error']}"

    collected = status.get("collected", 0)
    max_cubes = status.get("max_cubes", 15)
    delivered = status.get("delivered", {"red": 0, "green": 0, "blue": 0})
    mode = status.get("mode", "unknown")

    total_delivered = sum(delivered.values())
    completion = (total_delivered / max_cubes) * 100

    data = {
        "collected": collected,
        "max_cubes": max_cubes,
        "delivered": delivered,
        "total_delivered": total_delivered,
        "completion_percent": completion,
        "mode": mode,
        "is_complete": total_delivered >= max_cubes
    }

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)

    lines = [
        "# Task Progress",
        "",
        f"## Completion: {completion:.1f}%",
        "",
        f"**Cubes Collected**: {collected}",
        f"**Cubes Delivered**: {total_delivered}/{max_cubes}",
        "",
        "## By Color:",
        f"- 🔴 **RED**: {delivered.get('red', 0)}",
        f"- 🟢 **GREEN**: {delivered.get('green', 0)}",
        f"- 🔵 **BLUE**: {delivered.get('blue', 0)}",
        "",
        f"**Current Mode**: `{mode}`"
    ]

    if total_delivered >= max_cubes:
        lines.append("")
        lines.append("## ✅ TASK COMPLETE!")

    return "\n".join(lines)


@mcp.tool(
    name="webots_get_logs",
    annotations={
        "title": "Get Controller Logs",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def webots_get_logs(params: LogsInput) -> str:
    """
    Get recent log output from the YouBot controller.

    Retrieves the last N lines from the controller's log file, with optional
    text filtering to find specific events.

    Args:
        params: Number of lines and optional filter text

    Returns:
        Recent log entries

    Example:
        - Use when: "Show me the robot's logs"
        - Use when: "What errors occurred?"
    """
    log_file = LOGS_DIR / "controller.log"

    if not log_file.exists():
        return "No log file found. Ensure the controller is saving logs."

    try:
        with open(log_file, 'r') as f:
            all_lines = f.readlines()
    except Exception as e:
        return f"Error reading logs: {e}"

    # Filter if requested
    if params.filter_text:
        all_lines = [l for l in all_lines if params.filter_text.lower() in l.lower()]

    # Get last N lines
    lines = all_lines[-params.lines:]

    if not lines:
        return "No matching log entries found."

    result = ["# Controller Logs", ""]
    if params.filter_text:
        result.append(f"*Filtered by: '{params.filter_text}'*")
        result.append("")
    result.append(f"*Showing last {len(lines)} entries*")
    result.append("")
    result.append("```")
    result.extend([l.rstrip() for l in lines])
    result.append("```")

    return "\n".join(result)


@mcp.tool(
    name="webots_take_screenshot",
    annotations={
        "title": "Take Simulation Screenshot",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def webots_take_screenshot(params: ScreenshotInput) -> str:
    """
    Request a screenshot of the Webots simulation window.

    Sends a command to the controller to capture the current simulation view.
    The screenshot is saved to the screenshots directory.

    Args:
        params: Optional custom filename

    Returns:
        Path to the saved screenshot

    Example:
        - Use when: "Take a screenshot of the simulation"
        - Use when: "Capture the current view"
    """
    filename = params.save_path or f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    cmd = {
        "action": "screenshot",
        "filename": filename
    }

    if _write_command(cmd):
        expected_path = SCREENSHOTS_DIR / f"{filename}.png"
        return f"Screenshot requested. Will be saved to: `{expected_path}`\n\nWait a few seconds then use the Read tool to view it."
    else:
        return "Error: Failed to send screenshot command."


@mcp.tool(
    name="webots_simulation_control",
    annotations={
        "title": "Control Simulation",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def webots_simulation_control(params: SimulationCommandInput) -> str:
    """
    Control the Webots simulation state.

    Available commands:
    - pause: Pause the simulation
    - resume: Resume simulation (real-time mode)
    - reset: Reset the world to initial state
    - step: Execute a single simulation step

    Args:
        params: The command to execute

    Returns:
        Confirmation of command sent
    """
    cmd = {
        "action": "simulation_control",
        "command": params.command
    }

    if _write_command(cmd):
        return f"Command `{params.command}` sent to simulation."
    else:
        return f"Error: Failed to send {params.command} command."


@mcp.tool(
    name="webots_get_arm_state",
    annotations={
        "title": "Get Arm State",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def webots_get_arm_state(params: ResponseFormatInput) -> str:
    """
    Get the current state of the YouBot's robotic arm and gripper.

    Shows arm joint positions and gripper state (open/closed).

    Args:
        params: Response format options

    Returns:
        Arm and gripper state information
    """
    status = _load_status()

    if "error" in status:
        return f"Error: {status['error']}"

    arm = status.get("arm", {})
    gripper = status.get("gripper", {})

    if params.response_format == ResponseFormat.JSON:
        return json.dumps({"arm": arm, "gripper": gripper}, indent=2)

    lines = ["# Arm & Gripper State", ""]

    # Gripper
    gripper_state = gripper.get("state", "unknown")
    gripper_icon = "✊" if gripper_state == "closed" else "🖐️"
    lines.append(f"**Gripper**: {gripper_icon} {gripper_state}")

    has_cube = gripper.get("has_cube", False)
    if has_cube:
        cube_color = gripper.get("cube_color", "unknown")
        color_emoji = {"red": "🔴", "green": "🟢", "blue": "🔵"}.get(cube_color, "⚪")
        lines.append(f"**Holding**: {color_emoji} {cube_color} cube")

    # Arm joints
    if arm:
        lines.append("")
        lines.append("## Arm Joints:")
        for joint, value in arm.items():
            lines.append(f"- {joint}: {value:.2f}°")

    return "\n".join(lines)


@mcp.tool(
    name="webots_get_full_state",
    annotations={
        "title": "Get Full Robot State",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def webots_get_full_state(params: EmptyInput) -> str:
    """
    Get complete robot state snapshot for debugging.

    Returns ALL available data: pose, sensors, task progress, arm state,
    and navigation info in a single comprehensive view.

    Returns:
        Complete robot state as JSON

    Example:
        - Use when: "Give me everything about the robot"
        - Use when: "Full debug info please"
    """
    status = _load_status()

    if "error" in status:
        return f"Error: {status['error']}"

    result = json.dumps(status, indent=2)

    if len(result) > CHARACTER_LIMIT:
        return f"Status data truncated (too large):\n\n{result[:CHARACTER_LIMIT]}\n\n... [truncated]"

    return f"# Full Robot State\n\n```json\n{result}\n```"


# Run the server
if __name__ == "__main__":
    mcp.run()
