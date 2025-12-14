# Webots MCP Server

Generic MCP (Model Context Protocol) server for monitoring and controlling **any** Webots robot simulation. Provides Claude Code with real-time access to robot state, sensors, camera, and simulation control.

## Features

- **Real-time Monitoring**: Robot pose, mode, custom state fields
- **Sensor Data**: Any sensors your controller publishes
- **Camera**: View camera frames saved by controller
- **Simulation Control**: Pause, resume, reset, reload, step
- **Logging**: Controller logs with filtering
- **Screenshots**: Capture simulation views

## Quick Start

### 1. Install

```bash
pip install mcp pydantic
```

### 2. Configure Claude Code

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

### 3. Add to Your Controller

Minimal integration (~10 lines):

```python
import sys
sys.path.insert(0, "/path/to/webots-youbot-mcp")
from mcp_bridge import MCPBridge

# In __init__:
self.mcp = MCPBridge(self.robot)  # pass Robot or Supervisor

# In main loop:
self.mcp.publish({
    "pose": [x, y, theta],
    "mode": "navigate",
    "sensors": {"front": 0.5, "left": 1.2},
    # ... any fields you want to expose
})
self.mcp.get_command()  # handles simulation control
```

That's it! The bridge handles throttling, file I/O, and command processing.

## Available Tools

| Tool | Description |
|------|-------------|
| `webots_get_robot_state` | Get current robot state (pose, mode, etc.) |
| `webots_get_sensors` | Get sensor data from status |
| `webots_get_camera` | Get latest camera frame path |
| `webots_get_logs` | Get controller logs |
| `webots_simulation_control` | Pause/resume/reset/reload/step |
| `webots_take_screenshot` | Capture simulation view |
| `webots_monitor` | Monitor robot for N seconds |
| `webots_get_full_state` | Complete state dump |

## MCPBridge API

```python
bridge = MCPBridge(robot, data_dir=None)

# Publish state (call every timestep)
bridge.publish({"key": "value", ...})

# Check for commands (optional)
cmd = bridge.get_command()

# Log messages
bridge.log("message")

# Save camera frames (optional)
bridge.save_camera_frame(camera)
```

Built-in commands handled automatically:
- `simulation`: pause/resume/reset/reload/step
- `screenshot`: capture simulation view

## Data Directory

```
data/
├── status.json      # Robot state (written by controller)
├── commands.json    # Commands from MCP
├── camera/          # Camera frames
├── screenshots/     # Simulation screenshots
└── logs/            # Controller logs
```

## Requirements

- Python 3.10+
- `mcp` >= 1.0.0
- `pydantic` >= 2.0.0
- `Pillow` (optional, for camera frames)

## License

MIT
