from __future__ import annotations

import os
import queue
import threading
import time
from typing import Generator, Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, UInt8MultiArray


class RivaAsrNode(Node):
    def __init__(self) -> None:
        super().__init__("riva_asr")

        self.declare_parameter("input_topic", "/g1/mics/pcm16")
        self.declare_parameter("output_topic", "callboy/input_text")
        self.declare_parameter("sample_rate_hz", 16000)
        self.declare_parameter("channels", 1)
        self.declare_parameter("chunk_ms", 100)
        self.declare_parameter("queue_max_chunks", 200)

        self.declare_parameter("server", os.environ.get("RIVA_SERVER", "localhost:50051"))
        self.declare_parameter("use_ssl", False)
        self.declare_parameter("language_code", "de-DE")
        self.declare_parameter("model_name", "")
        self.declare_parameter("enable_automatic_punctuation", True)
        self.declare_parameter("profanity_filter", False)
        self.declare_parameter("interim_results", True)
        self.declare_parameter("print_interim", True)

        input_topic = self.get_parameter("input_topic").get_parameter_value().string_value
        output_topic = self.get_parameter("output_topic").get_parameter_value().string_value

        self._pub = self.create_publisher(String, output_topic, 10)
        self._sub = self.create_subscription(UInt8MultiArray, input_topic, self._on_audio, 10)

        self._buf = bytearray()
        self._stop = threading.Event()
        self._last_interim_len = 0

        max_chunks = int(self.get_parameter("queue_max_chunks").value)
        if max_chunks <= 0:
            max_chunks = 200
        self._q: "queue.Queue[Optional[bytes]]" = queue.Queue(maxsize=max_chunks)

        self.get_logger().info(
            "Ready. Subscribed to %s; streaming to Riva (%s); publishing final text to %s."
            % (input_topic, self.get_parameter("server").value, output_topic)
        )

        self._thread = threading.Thread(target=self._run_asr_loop, daemon=True)
        self._thread.start()

    def destroy_node(self):
        self._stop.set()
        try:
            self._q.put_nowait(None)
        except Exception:
            pass
        return super().destroy_node()

    def _bytes_per_chunk(self) -> int:
        sample_rate_hz = int(self.get_parameter("sample_rate_hz").value)
        channels = int(self.get_parameter("channels").value)
        chunk_ms = int(self.get_parameter("chunk_ms").value)

        if sample_rate_hz <= 0:
            sample_rate_hz = 16000
        if channels <= 0:
            channels = 1
        if chunk_ms <= 0:
            chunk_ms = 100

        # PCM16 -> 2 bytes per sample
        samples = int(sample_rate_hz * (chunk_ms / 1000.0))
        chunk_bytes = samples * channels * 2
        return max(chunk_bytes, 3200)

    def _enqueue_chunk(self, chunk: bytes) -> None:
        if not chunk:
            return
        try:
            self._q.put_nowait(chunk)
        except queue.Full:
            try:
                _ = self._q.get_nowait()
            except Exception:
                pass
            try:
                self._q.put_nowait(chunk)
            except Exception:
                pass

    def _on_audio(self, msg: UInt8MultiArray) -> None:
        if self._stop.is_set():
            return

        try:
            data = bytes(msg.data)
        except Exception:
            # Fallback: std_msgs might expose list-like data
            data = bytes(bytearray(msg.data))

        if not data:
            return

        self._buf.extend(data)

        chunk_bytes = self._bytes_per_chunk()
        while len(self._buf) >= chunk_bytes:
            chunk = bytes(self._buf[:chunk_bytes])
            del self._buf[:chunk_bytes]
            self._enqueue_chunk(chunk)

    def _audio_chunk_iterator(self) -> Generator[bytes, None, None]:
        while rclpy.ok() and not self._stop.is_set():
            try:
                item = self._q.get(timeout=0.1)
            except queue.Empty:
                continue
            if item is None:
                return
            yield item

    def _print_interim(self, text: str) -> None:
        if not bool(self.get_parameter("print_interim").value):
            return
        pad = " " * max(0, self._last_interim_len - len(text))
        print("\r" + text + pad, end="", flush=True)
        self._last_interim_len = len(text)

    def _print_final(self, text: str) -> None:
        if self._last_interim_len > 0:
            print("\r" + (" " * self._last_interim_len) + "\r", end="")
            self._last_interim_len = 0
        print(text, flush=True)

    def _publish_final(self, text: str) -> None:
        msg = String()
        msg.data = text
        self._pub.publish(msg)

    def _run_asr_loop(self) -> None:
        try:
            import riva.client  # type: ignore
        except ModuleNotFoundError as e:
            self.get_logger().error(
                f"Riva Python client is not available ({e}). Run this node in the same environment as the Riva examples, or install the Riva client package."
            )
            return
        except Exception as e:
            self.get_logger().error(f"Failed to import riva client: {e}")
            return

        server = self.get_parameter("server").get_parameter_value().string_value
        use_ssl = self.get_parameter("use_ssl").get_parameter_value().bool_value
        language_code = self.get_parameter("language_code").get_parameter_value().string_value
        model_name = self.get_parameter("model_name").get_parameter_value().string_value
        sample_rate_hz = int(self.get_parameter("sample_rate_hz").value)

        enable_punct = self.get_parameter("enable_automatic_punctuation").get_parameter_value().bool_value
        profanity_filter = self.get_parameter("profanity_filter").get_parameter_value().bool_value
        interim_results = self.get_parameter("interim_results").get_parameter_value().bool_value

        auth = riva.client.Auth(uri=server, use_ssl=use_ssl)
        asr_service = riva.client.ASRService(auth)

        config = riva.client.StreamingRecognitionConfig(
            config=riva.client.RecognitionConfig(
                encoding=riva.client.AudioEncoding.LINEAR_PCM,
                language_code=language_code,
                model=model_name,
                max_alternatives=1,
                profanity_filter=profanity_filter,
                enable_automatic_punctuation=enable_punct,
                sample_rate_hertz=sample_rate_hz,
                audio_channel_count=1,
            ),
            interim_results=interim_results,
        )

        self.get_logger().info(
            "ASR streaming started (server=%s, language=%s, sample_rate_hz=%s)."
            % (server, language_code, sample_rate_hz)
        )

        while rclpy.ok() and not self._stop.is_set():
            try:
                responses = asr_service.streaming_response_generator(
                    audio_chunks=self._audio_chunk_iterator(),
                    streaming_config=config,
                )

                for response in responses:
                    if self._stop.is_set():
                        break

                    results = getattr(response, "results", None)
                    if not results:
                        continue

                    for result in results:
                        alternatives = getattr(result, "alternatives", None)
                        if not alternatives:
                            continue

                        transcript = alternatives[0].transcript
                        if transcript is None:
                            continue

                        is_final = bool(getattr(result, "is_final", False))

                        if is_final:
                            text = transcript.strip()
                            if text:
                                self._print_final(text)
                                self._publish_final(text)
                        else:
                            self._print_interim(transcript.strip())

            except Exception as e:
                self.get_logger().error(f"ASR stream error: {e}; retrying in 1s")
                time.sleep(1.0)


def main() -> None:
    rclpy.init()
    node = RivaAsrNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            node.destroy_node()
        except Exception:
            pass
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
