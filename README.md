# Webots YouBot MCP Server

MCP (Model Context Protocol) server for monitoring and controlling a KUKA YouBot robot in Webots simulation. Provides Claude Code with real-time access to robot sensors, camera, navigation state, and simulation control.

## Features

- **Real-time Robot Monitoring**: Position, mode, task progress
- **Sensor Data Access**: 4 LIDARs, 8 distance sensors
- **Camera Integration**: View camera frames and recognized objects
- **Navigation Visualization**: Occupancy grid and path waypoints
- **Simulation Control**: Pause, resume, reset, step
- **Logging**: Controller logs with filtering

## Installation

```bash
cd webots-youbot-mcp
pip install -r requirements.txt
```

## Usage with Claude Code

### 1. Configure MCP Server

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "webots-youbot": {
      "command": "python",
      "args": ["/path/to/webots-youbot-mcp/webots_youbot_mcp_server.py"],
      "cwd": "/path/to/webots-youbot-mcp"
    }
  }
}
```

### 2. Integrate with YouBot Controller

Add the MCP bridge to your Webots controller:

```python
import sys
sys.path.insert(0, "/path/to/webots-youbot-mcp")
from mcp_bridge import MCPBridge

# In controller __init__:
self.mcp = MCPBridge(self.robot)

# In main loop:
self.mcp.update_status(
    pose=self.pose,
    mode=self.mode,
    collected=self.collected,
    lidar_data=lidar_info,
    recognized_objects=recognition_list,
    # ... other state
)
self.mcp.process_commands()
```

### 3. Use with Claude Code

Once configured, Claude Code can:

```
"What's the robot's current position?"
→ Calls webots_get_robot_status

"Show me the LIDAR readings"
→ Calls webots_get_lidar_readings

"How many cubes have been collected?"
→ Calls webots_get_task_progress

"Take a screenshot of the simulation"
→ Calls webots_take_screenshot

"Pause the simulation"
→ Calls webots_simulation_control
```

## Available Tools

| Tool | Description |
|------|-------------|
| `webots_get_robot_status` | Get robot pose, mode, and task state |
| `webots_get_lidar_readings` | Get all 4 LIDAR sensor data |
| `webots_get_distance_sensors` | Get 8 IR distance sensor values |
| `webots_get_camera_image` | Get latest camera frame path |
| `webots_get_recognized_objects` | Get detected cubes (color, distance, angle) |
| `webots_get_occupancy_grid` | Get ASCII map visualization |
| `webots_get_current_path` | Get navigation waypoints |
| `webots_get_task_progress` | Get cube collection progress |
| `webots_get_logs` | Get controller log output |
| `webots_take_screenshot` | Capture simulation view |
| `webots_simulation_control` | Pause/resume/reset simulation |
| `webots_get_arm_state` | Get arm and gripper state |
| `webots_get_full_state` | Get complete debug dump |

## Data Directory Structure

```
webots-youbot-mcp/
├── data/
│   ├── status.json      # Current robot state (written by controller)
│   ├── commands.json    # Commands from MCP server
│   ├── camera/          # Camera frames
│   ├── screenshots/     # Simulation screenshots
│   ├── logs/            # Controller logs
│   └── grid/            # Occupancy grid visualizations
├── webots_youbot_mcp_server.py  # MCP server
├── mcp_bridge.py                # Controller integration
└── requirements.txt
```

## Requirements

- Python 3.10+
- `mcp` >= 1.0.0
- `pydantic` >= 2.0.0
- `Pillow` >= 10.0.0 (optional, for camera frames)

## License

MIT
