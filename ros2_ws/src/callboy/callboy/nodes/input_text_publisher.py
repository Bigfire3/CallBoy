from __future__ import annotations

import io
import sys
import threading
from typing import Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from callboy.config import default_config_path


class InputTextPublisher(Node):
    def __init__(self) -> None:
        super().__init__("input_text_publisher")
        self._pub = self.create_publisher(String, "/plan/input_text", 10)

        # Kept for consistency with other nodes; currently not used.
        self.declare_parameter("config_path", default_config_path())
        self.declare_parameter("text", "")
        self.declare_parameter("once", False)

        initial_text = self.get_parameter("text").get_parameter_value().string_value
        once = self.get_parameter("once").get_parameter_value().bool_value

        if initial_text:
            self._publish(initial_text)
            if once:
                raise SystemExit(0)

        self._input_stream = self._open_input_stream()

        self.get_logger().info(
            "Ready. Type text and press Enter to publish to /plan/input_text (Ctrl-D to exit)."
        )
        self._thread = threading.Thread(target=self._stdin_loop, daemon=True)
        self._thread.start()

    def _open_input_stream(self) -> io.TextIOBase:
        # When launched via `ros2 launch`, the child process stdin is often not
        # connected to the interactive terminal. In that case try /dev/tty.
        try:
            if hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
                self.get_logger().info("Using stdin for interactive input.")
                return sys.stdin
        except Exception:
            pass

        try:
            stream = open("/dev/tty", "r", encoding="utf-8", errors="replace")
            self.get_logger().info("Using /dev/tty for interactive input (stdin is not a TTY).")
            return stream
        except Exception as e:
            self.get_logger().warn(
                "No interactive input available (stdin is not a TTY and /dev/tty could not be opened: "
                f"{e}). You can still publish via the 'text' parameter or run this node in a separate terminal."
            )
            return sys.stdin

    def _publish(self, text: str) -> None:
        msg = String()
        msg.data = text
        self._pub.publish(msg)
        self.get_logger().info(f"Published: {text!r}")

    def _stdin_loop(self) -> None:
        while rclpy.ok():
            line: Optional[str] = self._input_stream.readline()
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
