from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from callboy.config import default_config_path, load_config
from callboy.supported_commands import SUPPORTED_COMMANDS

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore


def _normalize_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _build_prompt(*, text: str, normalized: str) -> str:
    supported = ", ".join(SUPPORTED_COMMANDS)
    return (
        "You are a strict command planner for a Unitree G1 robot.\n"
        "Convert the user's German instruction into a JSON object.\n\n"
        "Rules:\n"
        "- Output ONLY JSON.\n"
        "- Use only supported command names.\n"
        "- If you cannot map part of the request, add it to 'unavailable'.\n"
        "- Prefer safe minimal plans.\n\n"
        "Supported commands:\n"
        "- set_velocity (requires param: \"vx vy omega duration\")\n"
        "- set_stand_height (requires param: \"height\")\n"
        "- set_swing_height (requires param: \"height\")\n"
        "- set_fsm_id (requires param: \"id\")\n"
        "- shake_hand (optional param: \"0\" or \"1\")\n"
        f"- other available names: {supported}\n\n"
        "For turning/motion use set_velocity with a finite duration and always follow with stop_move.\n"
        "German hints:\n"
        "- 'drehe dich nach links' / 'links drehen' => omega > 0\n"
        "- 'drehe dich nach rechts' / 'rechts drehen' => omega < 0\n"
        "set_velocity details:\n"
        "- vx: forward velocity (m/s)\n"
        "- vy: lateral velocity (m/s)\n"
        "- omega: yaw velocity (rad/s)\n"
        "- duration: seconds to move at this velocity\n\n"
        "Examples (do not output these literally, just follow the pattern):\n"
        "User: 'geh zwei meter vorwärts'\n"
        "JSON: {\"commands\":[{\"name\":\"set_velocity\",\"param\":\"0.5 0 0 4.0\"},{\"name\":\"stop_move\"}],\"unavailable\":[]}\n"
        "User: 'drehe dich nach links'\n"
        "JSON: {\"commands\":[{\"name\":\"set_velocity\",\"param\":\"0 0 0.6 1.2\"},{\"name\":\"stop_move\"}],\"unavailable\":[]}\n"
        "User: 'drehe dich nach rechts'\n"
        "JSON: {\"commands\":[{\"name\":\"set_velocity\",\"param\":\"0 0 -0.6 1.2\"},{\"name\":\"stop_move\"}],\"unavailable\":[]}\n\n"
        "Return format:\n"
        "{\n"
        "  \"commands\": [{\"name\": \"stand_up\"}, {\"name\": \"shake_hand\"}],\n"
        "  \"unavailable\": []\n"
        "}\n\n"
        f"User text: {text!r}\n"
        f"Normalized: {normalized!r}\n"
    )


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    # Fallback: try to extract first JSON object substring.
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON object found in model output")
    return json.loads(match.group(0))


class OllamaPlanner(Node):
    def __init__(self) -> None:
        super().__init__("ollama_planner")

        self.declare_parameter("config_path", default_config_path())
        cfg = load_config(self.get_parameter("config_path").get_parameter_value().string_value)

        self.declare_parameter("ollama_url", cfg.ollama.url)
        self.declare_parameter("ollama_model", cfg.ollama.model)
        self.declare_parameter("timeout_s", 60.0)

        self._sub = self.create_subscription(String, "callboy/input_text", self._on_text, 10)
        self._pub = self.create_publisher(String, "callboy/json", 10)

        ollama_url = self.get_parameter("ollama_url").get_parameter_value().string_value
        ollama_model = self.get_parameter("ollama_model").get_parameter_value().string_value
        self.get_logger().info(
            f"Planner ready (model={ollama_model!r})."
        )

        if requests is None:
            self.get_logger().error(
                "Python package 'requests' is missing. Install python3-requests or pip install requests."
            )

    def _ollama_generate(self, prompt: str) -> str:
        if requests is None:
            raise RuntimeError("requests is not available")

        url = self.get_parameter("ollama_url").get_parameter_value().string_value.rstrip("/")
        model = self.get_parameter("ollama_model").get_parameter_value().string_value
        timeout_s = self.get_parameter("timeout_s").get_parameter_value().double_value

        resp = requests.post(
            f"{url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
            },
            timeout=timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()
        out = data.get("response")
        if not isinstance(out, str):
            raise RuntimeError("Unexpected Ollama response shape")
        return out

    def _publish_json(self, obj: Dict[str, Any]) -> None:
        msg = String()
        msg.data = json.dumps(obj, ensure_ascii=False)
        self._pub.publish(msg)

    def _on_text(self, msg: String) -> None:
        text = msg.data
        normalized = _normalize_text(text)
        prompt = _build_prompt(text=text, normalized=normalized)

        try:
            model_out = self._ollama_generate(prompt)
            obj = _extract_json(model_out)
        except Exception as e:
            self.get_logger().error(f"Ollama planning failed: {e}")
            self._publish_json({"commands": [], "unavailable": ["ollama_error"]})
            return

        # Ensure minimal schema
        if "commands" not in obj:
            obj["commands"] = []
        if "unavailable" not in obj:
            obj["unavailable"] = []

        self._publish_json(obj)
        plan_json = json.dumps(obj, ensure_ascii=False)
        self.get_logger().info(f"Plan JSON: {plan_json}")


def main() -> None:
    rclpy.init()
    node = OllamaPlanner()
    try:
        rclpy.spin(node)
    finally:
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
