# IETF-127 MCP-Robotics

Last updated: **2026-11-09**

A navigation framework that accepts user intents and uses a **VLM to select tools and paths for controlling a ROS2 robot**.

## Architecture and Features

| Layer | Responsibilities |
|---|---|
| **Cloud** | Validate and normalize user intents, then forward them to Edge |
| **Edge** | YOLO–LiDAR fusion, VLM decision-making and replanning, MCP tools, and result reporting |
| **Robot Car** | Receive ROS2 sensor data, control motion, perform safety checks, and stop the robot |

- Convert natural-language coordinate commands into validated intents through `manager`
- Prioritize the user-specified speed; otherwise let the Edge VLM select a speed and record its explanation
- Validate and replan paths using map, LiDAR, and detected-object data
- Call T6 tools through the official MCP client using Streamable HTTP `tools/call`
- Compact repeated model history while retaining images, route candidates, and collision evidence
- Save one scenario JSON log and print the result to the terminal when a scenario ends

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

**Navigate using natural language** (run after T1–T6 are ready)

```bash
python3 -m manager.run "x:-16 y:0 좌표까지 이동 후 보고해줘" --send
```

If no numeric speed is provided, `manager` omits `constraints.speed_mps` so the Edge driving VLM selects it. To specify a speed:

```bash
python3 -m manager.run "x:-16 y:0 좌표까지 속도 0.2로 이동 후 보고해줘" --send
```

Without `--send`, the command saves an intent under `manager/outputs/` without sending it to Cloud. Currently, `manager` supports coordinate-based `move` requests with numeric x/y values.

`manager` translates and validates natural-language intents; the Edge VLM selects paths and speeds from observations.

The speed range is **0.01–0.35 m/s**; safety checks may slow or stop the robot.

**Report preference (`report`)**

| Natural-language request | Intent value | Edge behavior |
|---|---|---|
| “이동 후 보고해줘” (move and report) | `report:true` | Records the report request and includes the result in the `requested_report` field of `/health` |
| “이동하고 보고는 하지 마” (move without reporting) | `report:false` | The `requested_report` field of `/health` is `null` |

```bash
python3 -m manager.run "x:-16 y:0 좌표까지 이동하고 보고는 하지 마" --send
```

Maintenance JSON logs, T5 terminal results, and manual report queries remain available with `false`. Manager currently relies on the model to interpret this preference; the default and model-failure fallback are `true`. Preview the generated value by omitting `--send`.

**Query status and results** — replace `for_intent_id` with the actual intent ID printed by manager.

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

Navigation results are stored in scenario logs; intent generation and delivery are recorded separately under `manager/outputs/`.

Latest Isaac Sim navigation evidence: **`20261109_190648_553134_0001.json`** (`move_003`, `qwen3-vl:4b-instruct`).

| Item | Verified Result |
|---|---|
| Actual MCP calls | Five successful `tools/call` requests covering observation, planning, and execution; matching server response IDs |
| Target / final position | map `(-16.0, 0.0)` / `(-16.0237, -0.1344)` |
| Position error / duration | **13.65 cm / 5 min 8 sec**, within the 15 cm tolerance |
| Navigation and speed | VLM selected **0.2 m/s**, saved its explanation, and executed four detour waypoints |
| Path/response validation | Planning and execution checks passed; one malformed model response was rejected and corrected |
| Context handling | History compaction applied; maximum input **5,551 / 8,192 tokens**, no context overflow |
| Successful completion | Measured arrival and stop verified, intent closed, **100%** progress, `remaining_path:[]` |

The `speed_decision_result` event records `speed_mps` and `speed_reason`. Final success is independently verified from measured position and stopped motion.

Cloud–Edge communication uses HTTP JSON. The standard A2A protocol has not yet been implemented.
