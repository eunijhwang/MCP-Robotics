"""Validate LLM output and enforce the values extracted from the user text."""
from .config import (
    ALLOWED_ACTIONS,
    DEFAULT_SAFETY_MARGIN_M,
    DEFAULT_SPEED_MPS,
    FRAME_ID,
)


class SchemaError(ValueError):
    """LLM output does not have the expected shape."""


def check_shape(obj) -> dict:
    """Return the inner intent dict, or raise SchemaError."""
    if not isinstance(obj, dict) or not isinstance(obj.get("intent"), dict):
        raise SchemaError("missing top-level 'intent' object")
    intent = obj["intent"]
    loc = intent.get("target_location")
    if not isinstance(loc, dict):
        raise SchemaError("missing target_location")
    for k in ("x", "y"):
        v = loc.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise SchemaError(f"target_location.{k} must be a number, got {v!r}")
    return intent


def finalize(intent: dict, extracted: dict, seq: int):
    """
    Build the final intent. Returns (result, corrections).
    x/y/speed/margin always come from the user text (or defaults), so a wrong
    LLM number can never reach the robot; each override is reported.
    """
    corrections = []

    loc = intent["target_location"]
    for k in ("x", "y"):
        if float(loc[k]) != extracted[k]:
            corrections.append(f"{k}: llm={loc[k]} -> input={extracted[k]}")

    if intent.get("action") not in ALLOWED_ACTIONS:
        corrections.append(f"action: llm={intent.get('action')!r} -> 'move'")

    cons = intent.get("constraints") if isinstance(intent.get("constraints"), dict) else {}
    margin = extracted.get("safety_margin_m", DEFAULT_SAFETY_MARGIN_M)
    speed = extracted.get("speed_mps", DEFAULT_SPEED_MPS)
    if cons.get("safety_margin_m") != margin:
        corrections.append(f"safety_margin_m: llm={cons.get('safety_margin_m')} -> {margin}")
    if cons.get("speed_mps") != speed:
        corrections.append(f"speed_mps: llm={cons.get('speed_mps')} -> {speed}")

    report = intent.get("report")
    if not isinstance(report, bool):
        corrections.append(f"report: llm={report!r} -> True")
        report = True

    result = {
        "intent": {
            "intent_id": f"move_{seq:03d}",
            "action": "move",
            "target_location": {"x": extracted["x"], "y": extracted["y"], "frame_id": FRAME_ID},
            "constraints": {"safety_margin_m": margin, "speed_mps": speed},
            "report": report,
        }
    }
    return result, corrections


def from_input_only(extracted: dict, seq: int) -> dict:
    """Rule-based result used when the LLM is unavailable or keeps failing."""
    result, _ = finalize(
        {"target_location": {"x": extracted["x"], "y": extracted["y"]}, "report": True},
        extracted,
        seq,
    )
    return result
