from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from callboy.config import default_config_path, load_config

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore
def _build_prompt(*, prompt_template: str, text: str) -> str:
    template = prompt_template.rstrip() + "\n\n"
    return template + f"User text: {text!r}\n"


def _load_prompt_template(*, prompt_file: str, config_path: str) -> str:
    prompt_file = (prompt_file or "").strip()
    if not prompt_file:
        prompt_file = "prompts/default.txt"

    candidates: List[str]
    if os.path.isabs(prompt_file):
        candidates = [prompt_file]
    else:
        candidates = [os.path.join(os.path.dirname(config_path), prompt_file)]
        try:
            from ament_index_python.packages import get_package_share_directory  # type: ignore

            share_dir = get_package_share_directory("callboy")
            candidates.append(os.path.join(share_dir, prompt_file))
            candidates.append(os.path.join(share_dir, "prompts", prompt_file))
        except Exception:
            pass

    for path in candidates:
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                template = f.read()
            if not template.strip():
                raise RuntimeError(f"Prompt file is empty: {path}")
            return template

    raise RuntimeError(
        f"Prompt file not found: planner.prompt_file={prompt_file!r} (checked: {candidates})"
    )


ALLOWED_COMMANDS = {
    "set_velocity",
    "shake_hand",
    "wave_hand",
    "wave_hand_with_turn",
}


def _normalize_commands(obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = obj.get("commands")
    if not isinstance(raw, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str):
            continue
        name = name.strip()
        if name not in ALLOWED_COMMANDS:
            continue

        out_item: Dict[str, Any] = {"name": name}
        if name == "set_velocity":
            param = item.get("param")
            if isinstance(param, str) and param.strip():
                out_item["param"] = param.strip()
            else:
                # Invalid velocity command without parameters.
                continue
        else:
            # Gesture commands may optionally include a param.
            param = item.get("param")
            if isinstance(param, str) and param.strip():
                out_item["param"] = param.strip()

        normalized.append(out_item)

    # Safety: automatically append stop_move after each set_velocity.
    safe: List[Dict[str, Any]] = []
    for cmd in normalized:
        safe.append(cmd)
        if cmd.get("name") == "set_velocity":
            safe.append({"name": "stop_move"})

    return safe


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
        config_path = self.get_parameter("config_path").get_parameter_value().string_value
        cfg = load_config(config_path)

        self._prompt_template = _load_prompt_template(
            prompt_file=cfg.planner.prompt_file,
            config_path=config_path,
        )
        self.get_logger().info(f"Planner prompt loaded (planner.prompt_file={cfg.planner.prompt_file!r}).")

        self.declare_parameter("ollama_url", cfg.ollama.url)
        self.declare_parameter("ollama_model", cfg.ollama.model)
        self.declare_parameter("timeout_s", 60.0)

        self._sub = self.create_subscription(String, "callboy/input_text", self._on_text, 10)
        self._pub = self.create_publisher(String, "callboy/json", 10)

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
        prompt = _build_prompt(prompt_template=self._prompt_template, text=text)

        try:
            model_out = self._ollama_generate(prompt)
            self.get_logger().info(f"Ollama raw:\n{model_out}")
            obj = _extract_json(model_out)
            if not isinstance(obj, dict):
                raise ValueError("Model output JSON is not an object")
        except Exception as e:
            self.get_logger().error(f"Ollama planning failed: {e}")
            return

        # Normalize and restrict commands to the allowed set.
        filtered_commands = _normalize_commands(obj)
        obj = {
            "commands": filtered_commands
        }

        self._publish_json(obj)
        plan_json = json.dumps(obj, ensure_ascii=False)
        self.get_logger().info(f"{plan_json}")


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
