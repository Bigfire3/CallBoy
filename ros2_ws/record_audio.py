import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from std_msgs.msg import UInt8MultiArray
import wave
import time
import sys

class AudioRecorder(Node):
    def __init__(self):
        super().__init__('audio_recorder')
        
        # QoS Profile passend zum Publisher (oft Best Effort bei Audio)
        qos_profile = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT
        )

        self.subscription = self.create_subscription(
            UInt8MultiArray,
            '/g1/mics/pcm16',
            self.listener_callback,
            qos_profile
        )
        
        self.frames = []
        self.start_time = None
        self.duration = 30  # Sekunden
        self.get_logger().info("Warte auf Audio-Daten...")

    def listener_callback(self, msg):
        if self.start_time is None:
            self.start_time = time.time()
            self.get_logger().info("Aufnahme gestartet! (30 Sekunden)")

        # Daten sammeln
        # msg.data ist eine Liste von ints (uint8), muessen in bytes konvertiert werden
        self.frames.append(bytes(msg.data))

        elapsed = time.time() - self.start_time
        if elapsed > self.duration:
            self.get_logger().info("Aufnahme fertig.")
            raise SystemExit

def main(args=None):
    rclpy.init(args=args)
    recorder = AudioRecorder()

    try:
        rclpy.spin(recorder)
    except SystemExit:
        pass
    except KeyboardInterrupt:
        pass
    finally:
        if not recorder.frames:
            print("Keine Daten empfangen!")
        else:
            print(f"Speichere {len(recorder.frames)} Chunks in 'test_audio.wav'...")
            # Parameter: 16kHz, 1 Kanal, 16-bit
            wf = wave.open("test_audio.wav", 'wb')
            wf.setnchannels(1)
            wf.setsampwidth(2) # 16 bit = 2 bytes
            wf.setframerate(16000)
            wf.writeframes(b''.join(recorder.frames))
            wf.close()
            print("Datei 'test_audio.wav' gespeichert.")

        recorder.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
