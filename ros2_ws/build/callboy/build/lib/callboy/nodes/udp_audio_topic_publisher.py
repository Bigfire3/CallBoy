import socket
import struct
import threading
from array import array

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from std_msgs.msg import UInt8MultiArray, MultiArrayDimension


class UdpAudioTopicPublisher(Node):
    def __init__(self) -> None:
        super().__init__("udp_audio_topic_publisher")

        self.declare_parameter("mcast_group", "239.168.123.161")
        self.declare_parameter("port", 5555)
        self.declare_parameter("local_ip", "192.168.123.164")
        self.declare_parameter("topic", "/g1/mics/pcm16")
        self.declare_parameter("recv_bytes", 65535)
        self.declare_parameter("header_skip_bytes", 0)
        self.declare_parameter("channels", 1)
        self.declare_parameter("sample_width_bytes", 2)
        self.declare_parameter("best_effort", True)
        self.declare_parameter("qos_depth", 10)

        topic = self.get_parameter("topic").value
        depth = int(self.get_parameter("qos_depth").value)
        best_effort = bool(self.get_parameter("best_effort").value)

        qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=depth,
            reliability=ReliabilityPolicy.BEST_EFFORT if best_effort else ReliabilityPolicy.RELIABLE,
        )
        self.pub = self.create_publisher(UInt8MultiArray, topic, qos)

        self._sock = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._recv_loop, daemon=True)

        self.get_logger().info(
            "UDP->ROS2 audio publisher starting. "
            "Set parameters 'channels', 'sample_width_bytes', 'header_skip_bytes' to match the stream."
        )
        self._thread.start()

    def destroy_node(self):
        self._stop.set()
        try:
            if self._sock is not None:
                self._sock.close()
        except Exception:
            pass
        return super().destroy_node()

    def _open_socket(self) -> socket.socket:
        mcast_group = self.get_parameter("mcast_group").value
        port = int(self.get_parameter("port").value)
        local_ip = self.get_parameter("local_ip").value

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        
        # Increase receive buffer to prevent packet loss
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", port))
        mreq = struct.pack("4s4s", socket.inet_aton(mcast_group), socket.inet_aton(local_ip))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.settimeout(1.0)
        return sock

    def _recv_loop(self) -> None:
        recv_bytes = int(self.get_parameter("recv_bytes").value)

        try:
            self._sock = self._open_socket()
        except Exception as e:
            self.get_logger().error(f"Failed to open multicast socket: {e}")
            return

        warned_divisibility = False

        while rclpy.ok() and not self._stop.is_set():
            try:
                payload, _addr = self._sock.recvfrom(recv_bytes)
            except socket.timeout:
                continue
            except Exception as e:
                self.get_logger().error(f"Socket recv failed: {e}")
                break

            header_skip = int(self.get_parameter("header_skip_bytes").value)
            channels = int(self.get_parameter("channels").value)
            sample_width = int(self.get_parameter("sample_width_bytes").value)

            if header_skip < 0:
                header_skip = 0
            if header_skip > len(payload):
                continue

            audio_bytes = payload[header_skip:]

            msg = UInt8MultiArray()
            # Avoid per-byte Python ints when possible.
            msg.data = array("B", audio_bytes)

            if channels > 0 and sample_width > 0:
                denom = channels * sample_width
                if denom > 0 and (len(audio_bytes) % denom == 0):
                    frames = len(audio_bytes) // denom
                    dim_frames = MultiArrayDimension(label="frames", size=frames, stride=frames * denom)
                    dim_channels = MultiArrayDimension(label="channels", size=channels, stride=denom)
                    msg.layout.dim = [dim_frames, dim_channels]
                    msg.layout.data_offset = 0
                else:
                    if not warned_divisibility:
                        warned_divisibility = True
                        self.get_logger().warn(
                            "Audio payload size is not divisible by (channels*sample_width_bytes). "
                            "Layout metadata will be empty; adjust parameters to match stream."
                        )

            self.pub.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = UdpAudioTopicPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
