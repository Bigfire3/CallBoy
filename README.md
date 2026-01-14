# callboy (ROS2 + Ollama + Unitree SDK2)

Pipeline (Topics):
- `callboy/input_text` (String): German instruction from CLI
- `callboy/json` (String): planned command JSON from LLM

## Build

```bash
cd /home/unitree/callboy/ros2_ws
source /opt/ros/foxy/setup.bash
colcon build --symlink-install
source install/setup.bash
```

## Config (required)

The nodes require a config file at the default path:

- `/home/unitree/callboy/callboy.conf`

Or override the location via environment variable:

```bash
export CALLBOY_CONFIG=/absolute/path/to/callboy.conf
```

Expected keys (example):

```ini
[ollama]
url = http://localhost:11434
model = qwen2.5:3b-instruct

[sdk2]
cli_path = /home/unitree/unitree_sdk2/build/bin/g1_loco_client
network_interface = eth0
dry_run = true
```

## Run

If you see `bad_alloc caught: std::bad_alloc` when starting any ROS2 node, use CycloneDDS on loopback:

```bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///home/unitree/callboy/ros2_ws/cyclonedds_lo.xml
```

Terminal A (planner):

```bash
source /opt/ros/foxy/setup.bash
source /home/unitree/callboy/ros2_ws/install/setup.bash
ros2 run callboy callboy_ollama_planner
```

Terminal B (executor):

```bash
source /opt/ros/foxy/setup.bash
source /home/unitree/callboy/ros2_ws/install/setup.bash
ros2 run callboy callboy_sdk2_executor
```

Terminal C (CLI input publisher):

```bash
source /opt/ros/foxy/setup.bash
source /home/unitree/callboy/ros2_ws/install/setup.bash
ros2 run callboy callboy_input_text
```

Type a German command and press Enter.

### Run via launch (recommended)

Starts planner + executor + input node (no launch arguments required):

```bash
source /opt/ros/foxy/setup.bash
source /home/unitree/callboy/ros2_ws/install/setup.bash
ros2 launch callboy callboy.launch.py
```

## Notes

- If `ros2` isn't found, you likely forgot `source /opt/ros/foxy/setup.bash`.
- If you want to test without moving the robot, start the executor with `-p dry_run:=true`.
- Defaults can be set in `CALLBOY_CONFIG` (or edit `/home/unitree/callboy/callboy.conf`). ROS params can override config values when running nodes manually.
# ros2/asr fresh start
