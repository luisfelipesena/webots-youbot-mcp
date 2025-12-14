# Webots MCP Server

Generic MCP (Model Context Protocol) bridge for **any** Webots robot simulation. Provides Claude Code and Cursor with real-time access to robot state, sensors, camera, and simulation control.

## Quick Start (3 Lines)

```python
from mcp_bridge import MCPBridge

bridge = MCPBridge(robot)  # Auto-detects Supervisor
bridge.publish({"pose": [x, y, theta], "mode": "navigate"})
```

That's it! Claude Code now has full visibility into your simulation.

## Installation

### Option 1: Clone (Recommended)

```bash
git clone https://github.com/luisfelipesena/webots-youbot-mcp.git
pip install mcp pydantic
```

### Option 2: Copy Files

Copy `mcp_bridge.py` to your controller directory.

## Claude Code Integration

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "webots": {
      "command": "python",
      "args": ["/path/to/webots-youbot-mcp/webots_youbot_mcp_server.py"],
      "cwd": "/path/to/webots-youbot-mcp"
    }
  }
}
```

## Cursor Integration

Same configuration - Cursor reads `.mcp.json` automatically.

## Controller Integration

### Minimal Example

```python
import sys
sys.path.insert(0, "/path/to/webots-youbot-mcp")
from mcp_bridge import MCPBridge

class MyController:
    def __init__(self):
        self.robot = Robot()  # or Supervisor()
        self.mcp = MCPBridge(self.robot)

    def run(self):
        while self.robot.step(32) != -1:
            # Your logic here
            self.mcp.publish({
                "pose": [x, y, theta],
                "mode": self.mode,
                "sensors": {"front": 1.2, "left": 0.8},
            })
            self.mcp.get_command()  # Handle simulation control
```

### Advanced: World Reload Detection

```python
def reset_state():
    """Called automatically when world reloads"""
    self.mode = "search"
    self.collected = 0

bridge = MCPBridge(robot)
bridge.on_reload(reset_state)

# In main loop:
bridge.detect_reload()  # Triggers callback if reload detected
```

### Advanced: Custom Commands

```python
def handle_custom(cmd):
    if cmd.get("action") == "my_action":
        print(f"Custom command: {cmd}")

bridge.register_command("my_action", handle_custom)
```

## Available MCP Tools

| Tool | Description |
|------|-------------|
| `webots_get_robot_state` | Get current robot state (pose, mode, etc.) |
| `webots_get_sensors` | Get sensor data from status |
| `webots_get_camera` | Get latest camera frame path |
| `webots_get_logs` | Get controller logs |
| `webots_simulation_control` | Pause/resume/reset/reload/step/fast |
| `webots_world_reload` | Force reload world (macOS: osascript) |
| `webots_world_reset` | Reset simulation to initial state |
| `webots_reset_controller_state` | Reset controller internal state |
| `webots_take_screenshot` | Capture simulation view |
| `webots_monitor` | Monitor robot for N seconds |
| `webots_get_full_state` | Complete state dump |

### Force Reload (macOS)

When controller is stuck, use force reload via osascript:

```python
# From MCP:
webots_world_reload(force=True)  # Sends Ctrl+Shift+R to Webots
webots_world_reset(force=True)   # Sends Ctrl+Shift+T to Webots
```

Requires accessibility permissions for Terminal/IDE in System Preferences.

## Data Directory Structure

```
data/
├── status.json      # Robot state (written by controller)
├── commands.json    # Commands from MCP
├── camera/          # Camera frames
├── screenshots/     # Simulation screenshots
└── logs/            # Controller logs
```

## MCPBridge API Reference

```python
bridge = MCPBridge(robot, data_dir=None, throttle_interval=5)

# Core
bridge.publish(state_dict)          # Publish state (throttled)
bridge.publish(state, force=True)   # Publish immediately
bridge.get_command()                # Check for MCP commands

# Reload Detection
bridge.on_reload(callback)          # Register reload callback
bridge.detect_reload()              # Check if world reloaded

# Custom Commands
bridge.register_command(action, handler)

# Utilities
bridge.log(message)                 # Write to log file
bridge.save_camera_frame(camera)    # Save camera image
```

## Global Installation (All Projects)

Add to `~/.config/claude/mcp.json` (Claude Code) or global Cursor settings:

```json
{
  "mcpServers": {
    "webots": {
      "command": "python",
      "args": ["/absolute/path/to/webots_youbot_mcp_server.py"],
      "cwd": "/absolute/path/to/webots-youbot-mcp"
    }
  }
}
```

## Requirements

- Python 3.10+
- `mcp` >= 1.0.0
- `pydantic` >= 2.0.0
- `Pillow` (optional, for camera frames)

## License

MIT
