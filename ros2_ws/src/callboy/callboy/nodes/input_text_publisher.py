from __future__ import annotations

import sys
import threading
from typing import Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class InputTextPublisher(Node):
    def __init__(self) -> None:
        super().__init__("input_text_publisher")
        self._pub = self.create_publisher(String, "callboy/input_text", 10)

        self.declare_parameter("text", "")
        self.declare_parameter("once", False)

        initial_text = self.get_parameter("text").get_parameter_value().string_value
        once = self.get_parameter("once").get_parameter_value().bool_value

        if initial_text:
            self._publish(initial_text)
            if once:
                raise SystemExit(0)

        self.get_logger().info(
            "Ready. Type text and press Enter to publish to callboy/input_text (Ctrl-D to exit)."
        )
        self._thread = threading.Thread(target=self._stdin_loop, daemon=True)
        self._thread.start()

    def _publish(self, text: str) -> None:
        msg = String()
        msg.data = text
        self._pub.publish(msg)
        self.get_logger().info(f"Published: {text!r}")

    def _stdin_loop(self) -> None:
        while rclpy.ok():
            line: Optional[str] = sys.stdin.readline()
            if line is None or line == "":
                try:
                    rclpy.shutdown()
                except Exception:
                    pass
                return
            text = line.strip("\n")
            if text.strip() == "":
                continue
            self._publish(text)


def main() -> None:
    rclpy.init()
    try:
        node = InputTextPublisher()
        rclpy.spin(node)
    except SystemExit:
        pass
    finally:
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
