#!/usr/bin/env python3
"""
MCP Server for Webots Simulation Monitoring.

A generic MCP server that provides Claude Code with real-time access to
ANY Webots simulation - automatically detects robots, sensors, and world structure.

Works with any robot type and sensor configuration.
"""

import json
import subprocess
import platform
from pathlib import Path
from typing import Optional, Dict, Any, List
from enum import Enum
from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("webots_mcp")

# Constants
CHARACTER_LIMIT = 25000
DATA_DIR = Path(__file__).parent / "data"
STATUS_FILE = DATA_DIR / "status.json"
COMMANDS_FILE = DATA_DIR / "commands.json"
WORLD_INFO_FILE = DATA_DIR / "world_info.json"
CAMERA_DIR = DATA_DIR / "camera"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
LOGS_DIR = DATA_DIR / "logs"

# Ensure directories exist
for d in [DATA_DIR, CAMERA_DIR, SCREENSHOTS_DIR, LOGS_DIR]:
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


class SimulationCommandInput(BaseModel):
    """Input for simulation control commands."""
    model_config = ConfigDict(extra='forbid')
    command: str = Field(
        ...,
        description="Command: 'pause', 'resume', 'reset', 'reload', 'step'",
        pattern="^(pause|resume|reset|reload|step)$"
    )


class WorldReloadInput(BaseModel):
    """Input for world reload command."""
    model_config = ConfigDict(extra='forbid')
    force: bool = Field(
        default=False,
        description="Force reload using OS-level keyboard shortcut (macOS only). Use when controller is not responding."
    )


class MonitorInput(BaseModel):
    """Input for monitoring commands."""
    model_config = ConfigDict(extra='forbid')
    duration: int = Field(default=20, description="Duration in seconds to monitor", ge=1, le=120)


# ============== Helper Functions ==============

def _load_json(filepath: Path) -> Dict[str, Any]:
    """Load JSON file safely."""
    if not filepath.exists():
        return {"error": f"File not found: {filepath.name}"}
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {"error": f"Invalid JSON in {filepath.name}"}


def _write_command(cmd: Dict[str, Any]) -> bool:
    """Write command to commands.json."""
    try:
        cmd["timestamp"] = datetime.now().isoformat()
        with open(COMMANDS_FILE, 'w') as f:
            json.dump(cmd, f, indent=2)
        return True
    except Exception:
        return False


def _format_number(val: Any, decimals: int = 2) -> str:
    """Format number or return as-is."""
    if isinstance(val, (int, float)):
        return f"{val:.{decimals}f}"
    return str(val)


# ============== Tools ==============

@mcp.tool(
    name="webots_get_world_info",
    annotations={
        "title": "Get World Info",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def webots_get_world_info(params: ResponseFormatInput) -> str:
    """
    Get information about the current Webots world.

    Returns world name, all robots detected, their sensors, and scene structure.
    This is auto-detected from the simulation - works with any world file.

    Returns:
        World structure with robots and sensors
    """
    data = _load_json(WORLD_INFO_FILE)
    if "error" in data:
        return f"Error: {data['error']}. Run the MCP Supervisor controller in Webots first."

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)

    lines = ["# World Information", ""]
    lines.append(f"**World**: `{data.get('world_name', 'Unknown')}`")
    lines.append(f"**Time Step**: {data.get('time_step', 'N/A')}ms")
    lines.append("")

    robots = data.get("robots", [])
    if robots:
        lines.append(f"## Robots ({len(robots)})")
        for robot in robots:
            lines.append(f"\n### {robot.get('name', 'Unknown')}")
            lines.append(f"- **DEF**: `{robot.get('def_name', 'N/A')}`")
            lines.append(f"- **Type**: {robot.get('type', 'Robot')}")

            sensors = robot.get("sensors", {})
            if sensors:
                lines.append("- **Sensors**:")
                for sensor_type, sensor_list in sensors.items():
                    lines.append(f"  - {sensor_type}: {len(sensor_list)} ({', '.join(sensor_list[:5])}{'...' if len(sensor_list) > 5 else ''})")

    return "\n".join(lines)


@mcp.tool(
    name="webots_get_robot_state",
    annotations={
        "title": "Get Robot State",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def webots_get_robot_state(params: ResponseFormatInput) -> str:
    """
    Get current state of all robots in the simulation.

    Returns position, orientation, velocity, and custom state data
    published by each robot's controller.

    Returns:
        Robot states in requested format
    """
    data = _load_json(STATUS_FILE)
    if "error" in data:
        return f"Error: {data['error']}. Is the simulation running?"

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)

    lines = ["# Robot State", ""]

    # Timestamp
    ts = data.get("timestamp")
    if ts:
        lines.append(f"*Updated: {ts}*")
        lines.append("")

    # Robot-specific data
    robots = data.get("robots", {})
    if not robots:
        # Fallback: single robot format
        robots = {"main": data}

    for robot_name, state in robots.items():
        lines.append(f"## {robot_name}")

        # Position
        pose = state.get("pose", state.get("position", []))
        if pose:
            if len(pose) >= 3:
                import math
                lines.append(f"**Position**: ({pose[0]:.2f}, {pose[1]:.2f}) θ={math.degrees(pose[2]):.1f}°")
            elif len(pose) >= 2:
                lines.append(f"**Position**: ({pose[0]:.2f}, {pose[1]:.2f})")

        # Mode/State
        mode = state.get("mode", state.get("state"))
        if mode:
            lines.append(f"**Mode**: `{mode}`")

        # Custom fields
        for key, val in state.items():
            if key not in ("pose", "position", "mode", "state", "timestamp", "sensors", "robots"):
                if isinstance(val, dict):
                    lines.append(f"**{key}**: {json.dumps(val)}")
                elif isinstance(val, list):
                    lines.append(f"**{key}**: {len(val)} items")
                else:
                    lines.append(f"**{key}**: {val}")

        lines.append("")

    return "\n".join(lines)


@mcp.tool(
    name="webots_get_sensors",
    annotations={
        "title": "Get Sensor Data",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def webots_get_sensors(params: ResponseFormatInput) -> str:
    """
    Get all sensor readings from the simulation.

    Automatically detects and returns data from all sensors:
    LIDAR, Camera, DistanceSensor, GPS, Compass, etc.

    Returns:
        All sensor data organized by type
    """
    data = _load_json(STATUS_FILE)
    if "error" in data:
        return f"Error: {data['error']}"

    sensors = data.get("sensors", {})
    if not sensors:
        # Try alternative keys
        sensors = {}
        if "lidar_data" in data:
            sensors["lidar"] = data["lidar_data"]
        if "distance_sensors" in data:
            sensors["distance"] = data["distance_sensors"]
        if "recognized_objects" in data:
            sensors["camera"] = {"recognized_objects": data["recognized_objects"]}

    if not sensors:
        return "No sensor data available. Ensure the controller is publishing sensor data."

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(sensors, indent=2)

    lines = ["# Sensor Readings", ""]

    # LIDAR
    lidar = sensors.get("lidar", {})
    if lidar:
        lines.append("## LIDAR")
        for name, readings in lidar.items():
            if isinstance(readings, dict):
                min_dist = readings.get("min", readings.get("front", "N/A"))
                lines.append(f"- **{name}**: min={_format_number(min_dist)}m")
            else:
                lines.append(f"- **{name}**: {_format_number(readings)}m")
        lines.append("")

    # Distance Sensors
    distance = sensors.get("distance", sensors.get("distance_sensors", {}))
    if distance:
        lines.append("## Distance Sensors")
        for name, val in distance.items():
            if isinstance(val, (int, float)):
                icon = "🔴" if val < 100 else "🟡" if val < 300 else "🟢"
                lines.append(f"- **{name}**: {_format_number(val, 0)} {icon}")
        lines.append("")

    # Camera/Recognition
    camera = sensors.get("camera", {})
    if camera:
        lines.append("## Camera")
        objects = camera.get("recognized_objects", [])
        if objects:
            lines.append(f"Detected {len(objects)} objects:")
            for obj in objects[:10]:
                color = obj.get("color", "unknown")
                dist = obj.get("distance", 0)
                lines.append(f"- {color}: {_format_number(dist)}m")
        lines.append("")

    # Other sensors
    for sensor_type, sensor_data in sensors.items():
        if sensor_type not in ("lidar", "distance", "distance_sensors", "camera"):
            lines.append(f"## {sensor_type.title()}")
            if isinstance(sensor_data, dict):
                for k, v in sensor_data.items():
                    lines.append(f"- **{k}**: {v}")
            else:
                lines.append(f"- {sensor_data}")
            lines.append("")

    return "\n".join(lines)


@mcp.tool(
    name="webots_get_camera",
    annotations={
        "title": "Get Camera Image",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def webots_get_camera(params: EmptyInput) -> str:
    """
    Get the latest camera image from the simulation.

    Returns path to the most recent frame captured by any camera.

    Returns:
        Path to camera image file
    """
    frames = sorted(CAMERA_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not frames:
        return "No camera images available. Ensure camera capture is enabled."

    latest = frames[0]
    age = datetime.now().timestamp() - latest.stat().st_mtime

    lines = [
        "# Camera Frame",
        "",
        f"**File**: `{latest.name}`",
        f"**Path**: `{latest}`",
        f"**Age**: {age:.1f}s",
        "",
        "Use Read tool to view this image."
    ]

    return "\n".join(lines)


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
    Control the Webots simulation.

    Commands:
    - pause: Pause simulation
    - resume: Resume in real-time mode
    - reset: Reset to initial state
    - reload: Reload world file
    - step: Single simulation step

    Args:
        params: Command to execute

    Returns:
        Confirmation message
    """
    cmd = {"action": "simulation", "command": params.command}

    if _write_command(cmd):
        return f"✓ Command `{params.command}` sent to simulation."
    return f"✗ Failed to send `{params.command}` command."


def _send_webots_keystroke(keystroke: str, modifiers: List[str] = None) -> tuple[bool, str]:
    """
    Send keystroke to Webots application using osascript (macOS only).

    Args:
        keystroke: The key to press
        modifiers: List of modifiers ('command', 'control', 'shift', 'option')

    Returns:
        Tuple of (success, message)
    """
    if platform.system() != "Darwin":
        return False, "OS-level keystroke only supported on macOS"

    modifiers = modifiers or []
    modifier_str = ", ".join(modifiers) if modifiers else ""

    if modifier_str:
        applescript = f'''
        tell application "Webots"
            activate
        end tell
        delay 0.3
        tell application "System Events"
            keystroke "{keystroke}" using {{{modifier_str} down}}
        end tell
        '''
    else:
        applescript = f'''
        tell application "Webots"
            activate
        end tell
        delay 0.3
        tell application "System Events"
            keystroke "{keystroke}"
        end tell
        '''

    try:
        result = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return True, "Keystroke sent successfully"
        else:
            return False, f"osascript error: {result.stderr}"
    except subprocess.TimeoutExpired:
        return False, "osascript timed out"
    except Exception as e:
        return False, f"Error: {str(e)}"


@mcp.tool(
    name="webots_reset_controller_state",
    annotations={
        "title": "Reset Controller State",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def webots_reset_controller_state(params: EmptyInput) -> str:
    """
    Reset the robot controller's internal state without reloading the world.

    Resets collected count, delivered cubes, and mode to search.
    Useful when world was reloaded but controller kept its state.

    Returns:
        Status message
    """
    import asyncio

    cmd = {"action": "reset_state"}
    if _write_command(cmd):
        await asyncio.sleep(1)
        return "✓ Controller state reset command sent. Robot should restart in search mode."
    return "✗ Failed to write reset command."


@mcp.tool(
    name="webots_world_reload",
    annotations={
        "title": "Reload World",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def webots_world_reload(params: WorldReloadInput) -> str:
    """
    Reload the Webots world to restart the simulation.

    Two modes:
    - Default: Sends reload command via commands.json (requires running controller)
    - Force (macOS): Uses osascript to send Ctrl+Shift+R keystroke directly to Webots

    Args:
        params: Reload options

    Returns:
        Status message
    """
    import asyncio

    if params.force:
        # Use osascript to send Ctrl+Shift+R (World Reload shortcut)
        success, msg = _send_webots_keystroke("r", ["control", "shift"])
        if success:
            # Wait for reload to complete
            await asyncio.sleep(3)
            return "✓ World reload triggered via keystroke (Ctrl+Shift+R). Simulation should restart."
        else:
            return f"✗ Force reload failed: {msg}"
    else:
        # Standard method via commands.json
        cmd = {"action": "simulation", "command": "reload"}
        if _write_command(cmd):
            await asyncio.sleep(1)
            return "✓ Reload command sent. If controller is running, world will reload."
        return "✗ Failed to write reload command."


@mcp.tool(
    name="webots_world_reset",
    annotations={
        "title": "Reset Simulation",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def webots_world_reset(params: WorldReloadInput) -> str:
    """
    Reset the simulation to initial state (keeps world loaded).

    Two modes:
    - Default: Sends reset command via commands.json
    - Force (macOS): Uses osascript to send Ctrl+Shift+T keystroke

    Args:
        params: Reset options

    Returns:
        Status message
    """
    import asyncio

    if params.force:
        # Use osascript to send Ctrl+Shift+T (Simulation Reset shortcut)
        success, msg = _send_webots_keystroke("t", ["control", "shift"])
        if success:
            await asyncio.sleep(2)
            return "✓ Simulation reset triggered via keystroke (Ctrl+Shift+T)."
        else:
            return f"✗ Force reset failed: {msg}"
    else:
        cmd = {"action": "simulation", "command": "reset"}
        if _write_command(cmd):
            await asyncio.sleep(1)
            return "✓ Reset command sent."
        return "✗ Failed to write reset command."


@mcp.tool(
    name="webots_take_screenshot",
    annotations={
        "title": "Take Screenshot",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def webots_take_screenshot(params: EmptyInput) -> str:
    """
    Take a screenshot of the Webots simulation window.

    Returns:
        Path where screenshot will be saved
    """
    filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    cmd = {"action": "screenshot", "filename": filename}

    if _write_command(cmd):
        path = SCREENSHOTS_DIR / f"{filename}.png"
        return f"✓ Screenshot requested.\n\n**Path**: `{path}`\n\nWait 2-3 seconds, then use Read tool to view."
    return "✗ Failed to request screenshot."


@mcp.tool(
    name="webots_get_logs",
    annotations={
        "title": "Get Logs",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def webots_get_logs(params: LogsInput) -> str:
    """
    Get controller log output.

    Args:
        params: Number of lines and optional filter

    Returns:
        Recent log entries
    """
    log_file = LOGS_DIR / "controller.log"

    if not log_file.exists():
        return "No log file found."

    try:
        with open(log_file, 'r') as f:
            all_lines = f.readlines()
    except Exception as e:
        return f"Error reading logs: {e}"

    if params.filter_text:
        all_lines = [ln for ln in all_lines if params.filter_text.lower() in ln.lower()]

    lines = all_lines[-params.lines:]

    if not lines:
        return "No matching log entries."

    result = ["# Controller Logs", ""]
    if params.filter_text:
        result.append(f"*Filter: '{params.filter_text}'*")
    result.append(f"*Showing {len(lines)} entries*")
    result.append("")
    result.append("```")
    result.extend([ln.rstrip() for ln in lines])
    result.append("```")

    return "\n".join(result)


@mcp.tool(
    name="webots_monitor",
    annotations={
        "title": "Monitor Simulation",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def webots_monitor(params: MonitorInput) -> str:
    """
    Monitor simulation for specified duration and report behavior.

    Collects state snapshots over time to analyze robot behavior.

    Args:
        params: Duration to monitor (seconds)

    Returns:
        Analysis of robot behavior over time
    """
    import asyncio

    snapshots: List[Dict[str, Any]] = []
    interval = 2  # seconds between snapshots
    num_samples = params.duration // interval

    for _ in range(num_samples):
        data = _load_json(STATUS_FILE)
        if "error" not in data:
            data["sample_time"] = datetime.now().isoformat()
            snapshots.append(data)
        await asyncio.sleep(interval)

    if not snapshots:
        return "No data collected. Is the simulation running?"

    # Analyze
    lines = ["# Simulation Monitor Report", ""]
    lines.append(f"**Duration**: {params.duration}s ({len(snapshots)} samples)")
    lines.append("")

    # Track mode changes
    modes = [s.get("mode", s.get("robots", {}).get("main", {}).get("mode", "unknown")) for s in snapshots]
    mode_changes = []
    for i in range(1, len(modes)):
        if modes[i] != modes[i-1]:
            mode_changes.append(f"{modes[i-1]} → {modes[i]}")

    lines.append("## Mode Transitions")
    if mode_changes:
        for change in mode_changes:
            lines.append(f"- {change}")
    else:
        lines.append(f"- Stayed in `{modes[0]}` mode")
    lines.append("")

    # Track position
    positions = []
    for s in snapshots:
        pose = s.get("pose", s.get("robots", {}).get("main", {}).get("pose", []))
        if pose and len(pose) >= 2:
            positions.append((pose[0], pose[1]))

    if positions:
        import math
        total_dist = 0
        for i in range(1, len(positions)):
            dx = positions[i][0] - positions[i-1][0]
            dy = positions[i][1] - positions[i-1][1]
            total_dist += math.sqrt(dx*dx + dy*dy)

        lines.append("## Movement")
        lines.append(f"- **Start**: ({positions[0][0]:.2f}, {positions[0][1]:.2f})")
        lines.append(f"- **End**: ({positions[-1][0]:.2f}, {positions[-1][1]:.2f})")
        lines.append(f"- **Distance**: {total_dist:.2f}m")
        lines.append("")

    # Track collected (if present)
    collected_vals = [s.get("collected", 0) for s in snapshots]
    if any(collected_vals):
        lines.append("## Progress")
        lines.append(f"- **Collected**: {collected_vals[0]} → {collected_vals[-1]}")

        delivered = snapshots[-1].get("delivered", {})
        if delivered:
            for color, count in delivered.items():
                lines.append(f"- **{color}**: {count}")

    return "\n".join(lines)


@mcp.tool(
    name="webots_get_full_state",
    annotations={
        "title": "Get Full State",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def webots_get_full_state(params: EmptyInput) -> str:
    """
    Get complete simulation state as JSON for debugging.

    Returns all available data from status.json.

    Returns:
        Complete state dump
    """
    data = _load_json(STATUS_FILE)

    if "error" in data:
        return f"Error: {data['error']}"

    result = json.dumps(data, indent=2)
    if len(result) > CHARACTER_LIMIT:
        return f"```json\n{result[:CHARACTER_LIMIT]}\n```\n\n... [truncated]"

    return f"# Full State\n\n```json\n{result}\n```"


if __name__ == "__main__":
    mcp.run()
