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
ros2 run callboy callboy_ollama_planner \
	--ros-args -p ollama_model:=qwen2.5:3b-instruct -p ollama_url:=http://localhost:11434
```

Terminal B (executor):

```bash
source /opt/ros/foxy/setup.bash
source /home/unitree/callboy/ros2_ws/install/setup.bash
ros2 run callboy callboy_sdk2_executor \
	--ros-args -p sdk2_cli_path:=/home/unitree/unitree_sdk2/build/bin/g1_loco_client -p network_interface:=lo
```

Terminal C (CLI input publisher):

```bash
source /opt/ros/foxy/setup.bash
source /home/unitree/callboy/ros2_ws/install/setup.bash
ros2 run callboy callboy_input_text
```

Type a German command and press Enter.

## Notes

- If `ros2` isn't found, you likely forgot `source /opt/ros/foxy/setup.bash`.
- If you want to test without moving the robot, start the executor with `-p dry_run:=true`.
# ros2/asr fresh start
