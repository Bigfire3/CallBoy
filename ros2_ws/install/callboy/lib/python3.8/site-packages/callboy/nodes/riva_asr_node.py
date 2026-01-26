from __future__ import annotations

import math
import os
import queue
import struct
import threading
import time
from typing import Generator, Optional

import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String, UInt8MultiArray

from callboy.config import default_config_path, load_config


class RivaAsrNode(Node):
    def __init__(self) -> None:
        super().__init__("riva_asr")

        self.declare_parameter("config_path", default_config_path())
        cfg_file = self.get_parameter("config_path").get_parameter_value().string_value
        cfg = load_config(cfg_file)

        self.declare_parameter("input_topic", cfg.riva.input_topic)
        self.declare_parameter("output_topic", cfg.riva.output_topic)
        self.declare_parameter("sample_rate_hz", cfg.riva.sample_rate_hz)
        self.declare_parameter("channels", cfg.riva.channels)
        self.declare_parameter("chunk_ms", 100)
        self.declare_parameter("queue_max_chunks", 200)
        self.declare_parameter("best_effort", True)
        self.declare_parameter("qos_depth", 10)

        self.declare_parameter("server", cfg.riva.server)
        self.declare_parameter("use_ssl", False)
        self.declare_parameter("language_code", cfg.riva.language_code)
        self.declare_parameter("model_name", "")
        self.declare_parameter("enable_automatic_punctuation", cfg.riva.enable_automatic_punctuation)
        self.declare_parameter("profanity_filter", False)
        self.declare_parameter("interim_results", cfg.riva.interim_results)
        self.declare_parameter("print_interim", cfg.riva.print_interim)
        self.declare_parameter("vad_threshold", cfg.riva.vad_threshold)
        self.declare_parameter("wakeword", cfg.riva.wakeword)
        self.declare_parameter("log_rms", cfg.riva.log_rms)

        input_topic = self.get_parameter("input_topic").get_parameter_value().string_value
        output_topic = self.get_parameter("output_topic").get_parameter_value().string_value

        self._pub = self.create_publisher(String, output_topic, 10)

        depth = int(self.get_parameter("qos_depth").value)
        best_effort = bool(self.get_parameter("best_effort").value)
        if depth <= 0:
            depth = 10
        audio_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=depth,
            reliability=ReliabilityPolicy.BEST_EFFORT if best_effort else ReliabilityPolicy.RELIABLE,
        )
        self._sub = self.create_subscription(UInt8MultiArray, input_topic, self._on_audio, audio_qos)

        self._buf = bytearray()
        self._stop = threading.Event()
        self._last_interim_len = 0

        max_chunks = int(self.get_parameter("queue_max_chunks").value)
        if max_chunks <= 0:
            max_chunks = 200
        self._q: "queue.Queue[Optional[bytes]]" = queue.Queue(maxsize=max_chunks)

        self._last_rms_log = 0.0

        self.get_logger().info(
            "Streaming to Riva (%s); wakeword: %r"
            % (self.get_parameter("server").value, self.get_parameter("wakeword").value)
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

        # Simple RMS-based VAD / Noise Gate
        threshold = float(self.get_parameter("vad_threshold").value)
        if threshold > 0:
            count = len(chunk) // 2
            if count > 0:
                # Optimized RMS calc if possible, but keeping it simple
                shorts = struct.unpack("<%dh" % count, chunk)
                sum_sq = sum(s * s for s in shorts)
                rms = math.sqrt(sum_sq / count) / 32768.0
                
                now = time.time()
                if bool(self.get_parameter("log_rms").value) and (now - self._last_rms_log > 2.0):
                    self.get_logger().info(f"Audio RMS (Volume): {rms:.5f} (Gate: {threshold:.5f})")
                    self._last_rms_log = now

                if rms < threshold:
                    # Send silent chunk instead of skipping to keep the stream alive
                    chunk = b"\x00" * len(chunk)

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
        pad = " " * max(0, self._last_interim_len - len(text) - 11)
        print("\r>> " + text + pad, end="", flush=True)
        self._last_interim_len = len(text) + 11

    def _print_final(self, text: str) -> None:
        if self._last_interim_len > 0:
            print("\r" + (" " * (self._last_interim_len + 10)) + "\r", end="")
            self._last_interim_len = 0
        print("## " + text, flush=True)

    def _publish_final(self, text: str) -> None:
        wakeword = str(self.get_parameter("wakeword").value).strip()
        
        if wakeword:
            # Case-insensitive check for wakeword
            idx = text.lower().find(wakeword.lower())
            if idx == -1:
                return  # Wakeword not found, do not publish
            
            # Extract content after wakeword
            # We strip everything BEFORE the wakeword and the wakeword itself
            text = text[idx + len(wakeword):].strip()
            
            # If nothing is left after stripping, we don't publish a blank command
            if not text:
                return

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

        channels = int(self.get_parameter("channels").value)

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
                audio_channel_count=channels,
            ),
            interim_results=interim_results,
        )

        self.get_logger().info(
            "ASR started (language=%s)."
            % (language_code)
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
