# IETF-127 MCP-Robotics

Last updated: **2026-11-05**

A navigation framework that accepts user intents and uses a **VLM to select tools and paths for controlling a ROS2 robot**.

## Architecture and Features

| Layer | Responsibilities |
|---|---|
| **Cloud** | Validate and normalize user intents, then forward them to Edge |
| **Edge** | YOLO–LiDAR fusion, VLM decision-making and replanning, MCP tools, and result reporting |
| **Robot Car** | Receive ROS2 sensor data, control motion, perform safety checks, and stop the robot |

- Prioritize the user-specified speed; let the VLM select a speed when none is provided
- Validate and replan paths using map, LiDAR, and detected-object data
- Save one JSON log and print the result to the terminal when a scenario ends

## Runtime Environment

**Isaac Sim 4.5 · ROS2 Humble · Python 3.10 · Ollama**

Navigation was validated using `qwen3-vl:4b-instruct`. The default object detection weights are `detector/yolov8s.pt`.
Set up ROS2, Isaac Sim, and the Ollama server separately.

## Installation

Clone the repository, then run the following commands from the project root containing `requirements.txt` and `IETF127.env.sh`.

```bash
source /opt/ros/humble/setup.bash
python3 -m pip install -r requirements.txt
ollama pull qwen3-vl:4b-instruct
```

## Running the Project

Open `mapping/maps/isaac/full_warehouse_limo.usda` in Isaac Sim, enable ROS2 Bridge, and start playback.
Ensure that Isaac Sim and the ROS2 nodes use compatible DDS settings. **In each terminal, navigate to the project root** and apply the following settings.

```bash
source /opt/ros/humble/setup.bash
source ./IETF127.env.sh
export OLLAMA_MODEL=qwen3-vl:4b-instruct
```

Start each service in the following order, using a **separate terminal for each service**.

| Order | Command |
|---|---|
| T1 | `ros2 launch ./launch/vilar_frames.launch.py` |
| T2 | `python3 -m robot_car.imo_server_lidar` |
| T3 | `python3 -m robot_car.imo_control` |
| T4 | `python3 -m cloud.intent_server` |
| T5 | `python3 -m edge.edge_control` |
| T6 | `python3 -m edge.mcp_ros2_server` |

## Readiness Checks

Query the Edge status and confirm `pose_valid: true`, `perception.ready: true`, and `scan_error: null`.
When using a static map, also confirm `map.map_available: true`.

```bash
curl -sS http://127.0.0.1:8002/health
python3 -m edge.mcp_client
```

Confirm that the connection check prints `connected:true` and lists 12 tools.
The `mcp` field in Edge's `/health` response reflects Edge's most recent communication result, so it may show an unconnected state before the first tool call.

## Example Intent Requests

**Navigate to a target location** (example coordinates for the warehouse scene)

```bash
curl -sS -X POST http://127.0.0.1:5000/receive_intent \
  -H 'Content-Type: application/json' \
  -d '{"intent_id":"move_001","action":"move","target_location":{"x":-16.0,"y":0.0,"frame_id":"map"},"constraints":{"safety_margin_m":0.45,"speed_mps":0.2},"report":true}'
```

The allowed range for `speed_mps` is **0.01–0.35 m/s**.
Use a new `intent_id` for each new navigation request.

**Query status and results**

```bash
curl -sS -X POST http://127.0.0.1:5000/receive_intent \
  -H 'Content-Type: application/json' \
  -d '{"action":"report","for_intent_id":"move_001"}'
```

Request acceptance does not indicate successful navigation. Check the final report for `status: "succeeded"` and `success: true`.

**Request a stop**

```bash
curl -sS -X POST http://127.0.0.1:5000/receive_intent \
  -H 'Content-Type: application/json' \
  -d '{"intent_id":"stop_001","action":"stop"}'
```

## Logs and Validation

- Final log: `logs/scenarios/YYYYMMDD_HHMMSS_ffffff_0001.json`
- Terminal report: T5 prints the completion time, target and final positions, position error, and success status once when the scenario ends

JSON logs are saved and terminal results are printed regardless of the `report` setting.

Latest Isaac Sim navigation evidence: **`20261105_142601_978783_0001.json`**.

| Item | Verified Result |
|---|---|
| Actual MCP calls | `stop_robot → plan_path → execute_path`; all three calls succeeded, with matching correlation IDs and intent versions in server responses |
| Target / final position | map `(-16.0, 0.0)` / `(-16.0271, -0.1263)` |
| Position error / total duration | **12.92 cm / 4 min 2 sec** |
| Execution | User-specified speed of `0.35 m/s`; four detour waypoints executed in a single navigation operation |
| Successful completion | `success:true`, `stopped_verified:true`, `intent_closed:true`, 100% progress, and `remaining_path:[]` |

Cloud–Edge communication uses HTTP JSON. The standard A2A protocol has not yet been implemented.
