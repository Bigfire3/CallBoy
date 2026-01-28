import time
import threading
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from std_msgs.msg import String, UInt8MultiArray
from faster_whisper import WhisperModel
from callboy.config import load_config

# Constants that are now defaults, config overrides allow tuning
DEFAULT_SAMPLE_RATE = 16000

class CallboyWhisperASR(Node):
    def __init__(self):
        super().__init__("callboy_whisper_asr")
        
        # Load config
        try:
            self.cfg = load_config().whisper
        except Exception as e:
            self.get_logger().error(f"Failed to load config: {e}")
            raise e
        
        # Parameters from config
        model_size = self.cfg.model_size
        device = self.cfg.device
        compute_type = self.cfg.compute_type
        self.language = self.cfg.language
        if self.language == 'None': self.language = None
        
        # VAD Parameters
        self.silence_threshold = self.cfg.silence_threshold
        self.silence_duration = self.cfg.silence_duration
        self.min_speech_duration = self.cfg.min_speech_duration
        self.log_rms = self.cfg.log_rms

        self.get_logger().info(f"Loading Whisper Model: {model_size} on {device} ({compute_type})...")
        try:
            self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
            self.get_logger().info("Whisper Model loaded successfully!")
        except Exception as e:
            self.get_logger().error(f"Failed to load Whisper on {device}, falling back to CPU int8: {e}")
            self.model = WhisperModel(model_size, device="cpu", compute_type="int8")

        # Config
        self.buffer = b""
        self.lock = threading.Lock()
        self.is_speaking = False
        self.silence_start_time = None
        self.last_process_time = time.time()
        self.last_print_time = time.time()
        self.last_topic_check = 0.0
        
        # ROS
        qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT
        )
        self.sub = self.create_subscription(
            UInt8MultiArray, 
            self.cfg.input_topic, 
            self.audio_callback, 
            qos
        )
        self.pub_text = self.create_publisher(String, self.cfg.output_topic, 10)
        
        # Processing Thread
        self.running = True
        self.process_thread = threading.Thread(target=self.process_loop)
        self.process_thread.start()
        
        self.get_logger().info("Whisper ASR Node Ready. Waiting for audio...")

    def audio_callback(self, msg):
        """Receive raw PCM16 (Little Endian) bytes."""
        data = bytes(msg.data)
        with self.lock:
            self.buffer += data

    def process_loop(self):
        while self.running:
            time.sleep(0.1) # Check 10 times per second
            
            # Check if topic has publishers every 5 seconds
            now = time.time()
            if now - self.last_topic_check > 5.0:
                self.last_topic_check = now
                if self.count_publishers(self.cfg.input_topic) == 0:
                    self.get_logger().warning(f"No publishers found on topic '{self.cfg.input_topic}'. Is the audio source running?")

            with self.lock:
                if len(self.buffer) == 0:
                    continue
                # Copy buffer for analysis to avoid locking too long
                raw_bytes = self.buffer[:]
            
            # Convert to numpy int16
            audio_data = np.frombuffer(raw_bytes, dtype=np.int16)
            
            if len(audio_data) < DEFAULT_SAMPLE_RATE * 0.2: 
                continue # Too short to analyze

            # Simple Energy VAD
            # Compute RMS of the LAST chunk (e.g. last 0.2s)
            chunk_size = int(DEFAULT_SAMPLE_RATE * 0.2)
            recent_audio = audio_data[-chunk_size:]
            rms = np.sqrt(np.mean(recent_audio.astype(float)**2))
            
            # Debug: print volume every second
            if self.log_rms and (time.time() - self.last_print_time > 1.0):
                 self.get_logger().info(f"Audio RMS: {rms:.1f} (Threshold: {self.silence_threshold})")
                 self.last_print_time = time.time()

            is_loud = rms > self.silence_threshold
            
            if is_loud:
                if not self.is_speaking:
                    self.get_logger().info("Speech detected...")
                    self.is_speaking = True
                self.silence_start_time = None
            else:
                if self.is_speaking:
                    if self.silence_start_time is None:
                        self.silence_start_time = time.time()
                    
                    # Check if silence is long enough
                    if (time.time() - self.silence_start_time) > self.silence_duration:
                        self.get_logger().info("End of speech, transcribing...")
                        
                        # Grab valid speech segment
                        self.transcribe_buffer(audio_data)
                        
                        # Reset
                        self.is_speaking = False
                        self.silence_start_time = None
                        with self.lock:
                            self.buffer = b"" # Clear buffer after transcription

    def transcribe_buffer(self, int16_data):
        # Convert to float32 [-1, 1] for Whisper
        float_audio = int16_data.astype(np.float32) / 32768.0
        
        if len(float_audio) < DEFAULT_SAMPLE_RATE * self.min_speech_duration:
            self.get_logger().info("Audio too short, skipping.")
            return

        start_t = time.time()
        # Transcribe
        segments, info = self.model.transcribe(
            float_audio, 
            beam_size=1, 
            language=self.language,
            vad_filter=True # Use Whisper's internal VAD for better accuracy
        )
        
        full_text = " ".join([segment.text for segment in segments]).strip()
        dur = time.time() - start_t
        
        if full_text:
            self.get_logger().info(f"\n'{full_text}' ({dur:.2f}s)")
            # Publish
            msg = String()
            msg.data = full_text
            self.pub_text.publish(msg)
        else:
             self.get_logger().info("No speech recognized!")

    def destroy_node(self):
        self.running = False
        self.process_thread.join()
        super().destroy_node()

def main(args=None):
    rclpy.init(args=args)
    node = CallboyWhisperASR()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
