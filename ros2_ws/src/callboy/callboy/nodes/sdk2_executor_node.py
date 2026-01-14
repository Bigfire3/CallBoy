from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List, Tuple

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from callboy.command_schema import Command, Plan, plan_from_json_dict
from callboy.sdk2_executor import ExecutorConfig, execute_plan
from callboy.supported_commands import REQUIRES_PARAM, SUPPORTED_COMMANDS


def _validate_and_filter(plan: Plan) -> Tuple[Plan, List[str]]:
    supported = set(SUPPORTED_COMMANDS)
    dropped: List[str] = []
    kept: List[Command] = []

    for cmd in plan.commands:
        if cmd.name not in supported:
            dropped.append(f"unsupported:{cmd.name}")
            continue
        if cmd.name in REQUIRES_PARAM and (cmd.param is None or cmd.param.strip() == ""):
            dropped.append(f"missing_param:{cmd.name}")
            continue
        kept.append(cmd)

    merged_unavailable = list(plan.unavailable) + dropped
    return Plan(commands=kept, unavailable=merged_unavailable), dropped


class Sdk2ExecutorNode(Node):
    def __init__(self) -> None:
        super().__init__("sdk2_executor")

        self.declare_parameter("sdk2_cli_path", "/home/unitree/unitree_sdk2/build/bin/g1_loco_client")
        self.declare_parameter("network_interface", "lo")
        self.declare_parameter("timeout_s", 30.0)
        self.declare_parameter("dry_run", False)

        self._lock = threading.Lock()
        self._busy = False

        self._sub = self.create_subscription(String, "callboy/json", self._on_plan_json, 10)
        self.get_logger().info("Ready. Subscribed to callboy/json.")

    def _make_cfg(self) -> ExecutorConfig:
        sdk2_cli_path = self.get_parameter("sdk2_cli_path").get_parameter_value().string_value
        network_interface = self.get_parameter("network_interface").get_parameter_value().string_value
        timeout_s = self.get_parameter("timeout_s").get_parameter_value().double_value

        return ExecutorConfig(
            sdk2_cli_path=sdk2_cli_path,
            network_interface=network_interface,
            timeout_s=float(timeout_s),
        )

    def _on_plan_json(self, msg: String) -> None:
        with self._lock:
            if self._busy:
                self.get_logger().warn("Executor is busy; dropping incoming plan.")
                return
            self._busy = True

        thread = threading.Thread(target=self._execute_from_msg, args=(msg.data,), daemon=True)
        thread.start()

    def _execute_from_msg(self, json_text: str) -> None:
        try:
            obj: Dict[str, Any] = json.loads(json_text)
            plan = plan_from_json_dict(obj)
        except Exception as e:
            self.get_logger().error(f"Invalid plan JSON: {e}")
            with self._lock:
                self._busy = False
            return

        plan, dropped = _validate_and_filter(plan)
        if dropped:
            self.get_logger().warn(f"Dropped commands: {dropped}")
        if plan.unavailable:
            self.get_logger().warn(f"Plan unavailable items: {plan.unavailable}")

        cfg = self._make_cfg()
        if not os.path.exists(cfg.sdk2_cli_path):
            self.get_logger().error(f"sdk2_cli_path does not exist: {cfg.sdk2_cli_path}")
            with self._lock:
                self._busy = False
            return

        dry_run = self.get_parameter("dry_run").get_parameter_value().bool_value

        self.get_logger().info(
            f"Executing plan with {len(plan.commands)} commands via {cfg.sdk2_cli_path} (dry_run={dry_run})."
        )

        try:
            results = execute_plan(plan, cfg=cfg, dry_run=dry_run)
        except Exception as e:
            self.get_logger().error(f"Execution failed: {e}")
            with self._lock:
                self._busy = False
            return

        for res in results:
            out = (res.stdout or "").strip()
            err = (res.stderr or "").strip()
            if len(out) > 400:
                out = out[:400] + "..."
            if len(err) > 400:
                err = err[:400] + "..."
            self.get_logger().info(
                f"{res.command.name} rc={res.returncode} stdout={out!r} stderr={err!r}"
            )

        with self._lock:
            self._busy = False


def main() -> None:
    rclpy.init()
    node = Sdk2ExecutorNode()
    try:
        rclpy.spin(node)
    finally:
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
