
# callboy

ROS 2 (Python) Pipeline für Sprach-/Text-Eingaben → LLM-Planung (Ollama) → Ausführung von Unitree SDK2 CLI-Kommandos (z. B. für Unitree G1).

Die Komponenten sind so aufgebaut, dass Audio (PCM16) aus einer ROS-Topic oder aus UDP-Multicast in ROS 2 eingespeist wird, dann per ASR (Whisper oder optional NVIDIA Riva) zu Text transkribiert wird. Ein Planner-NODE wandelt den Text via Ollama in ein **striktes JSON** mit Kommandos um, und ein Executor-NODE ruft anschließend eine SDK2-CLI (Beispielbinary) mit passenden Flags auf.

## Architektur (Datenfluss)

Standard-Flow im Launch:

1. **Audio-In**: `callboy_udp_audio_topic`
	 - UDP Multicast → ROS Topic `/g1/mics/pcm16` (`std_msgs/UInt8MultiArray`, PCM16 little-endian)
2. **ASR**: `callboy_whisper_asr` *(alternativ: `callboy_riva_asr`)*
	 - `/g1/mics/pcm16` → `callboy/input_text` (`std_msgs/String`)
3. **Planner**: `callboy_ollama_planner`
	 - `callboy/input_text` → `callboy/json` (`std_msgs/String`, JSON)
4. **Executor**: `callboy_sdk2_executor`
	 - `callboy/json` → SDK2 CLI Aufrufe (Subprocess)

## Workspace-Struktur

- `callboy.conf`: zentrale Konfiguration (Standard-Pfad wird vom Code erwartet; siehe unten)
- `ros2_ws/`: ROS2 Workspace
	- `src/callboy/`: ROS2 Python Package `callboy`
		- `callboy/nodes/*`: ROS Nodes
		- `launch/callboy.launch.py`: Standard-Launch
		- `prompts/*`: Prompt-Templates für den Planner
	- `cyclonedds_lo.xml`, `fastdds_no_shm.xml`: DDS/Transport Profile (optional)
	- `record_audio.py`: Helper zum Mitschneiden der Audio-Topic als WAV

## Voraussetzungen

- ROS 2 (mit `rclpy`, `launch`, `launch_ros`)
- `colcon` Build-Tools
- Python Dependencies (mindestens):
	- `requests` (Planner → Ollama)
	- `faster-whisper` (Whisper ASR)
	- `numpy` (Whisper ASR verarbeitet PCM)
- Optional:
	- NVIDIA Riva Python Client (`riva.client`) für `callboy_riva_asr`
	- Lokaler Ollama Server (Standard: `http://localhost:11434`)
	- Unitree SDK2 Beispiel-CLI Binary (z. B. `g1_loco_client`)

Hinweis: `setup.py` listet aktuell `faster-whisper` als `install_requires`. `numpy` wird im Whisper-Node verwendet, sollte also ebenfalls im Environment vorhanden sein.

## Build & Installation (ROS2)

Im Workspace bauen:

```bash
cd ros2_ws
colcon build --symlink-install
source install/setup.bash
```

## Konfiguration (`callboy.conf`)

Die Nodes laden ihre Konfiguration über `CALLBOY_CONFIG` oder einen Default-Pfad.

- Default im Code: `CALLBOY_CONFIG` oder sonst `/home/unitree/callboy/callboy.conf`
- Empfehlung für dieses Repo:

```bash
export CALLBOY_CONFIG="$PWD/callboy.conf"
```

### Wichtige Abschnitte

#### `[ollama]`

- `url`: Basis-URL des Ollama Servers (z. B. `http://localhost:11434`)
- `model`: Modellname wie in `ollama list`

#### `[planner]`

- `prompt_file`: Prompt-Datei (relativ zur Config-Datei oder aus Package-Share)
	- Auflösung im Planner:
		1) absoluter Pfad, sonst
		2) relativ zu dem Ordner der `callboy.conf`, sonst
		3) aus `share/callboy/...` (ament package share)

#### `[sdk2]`

- `cli_path`: Pfad zur SDK2 CLI Binary (muss existieren)
- `network_interface`: Interface für DDS/SDK2 (häufig `eth0`)
- `dry_run`: `true` verhindert echte Ausführung (Sicherheitsmodus)

#### `[whisper]`

- `model_size`: z. B. `turbo`, `small`, …
- `device`: `cuda` oder `cpu`
- `compute_type`: z. B. `int8`, `int8_float16`
- `language`: z. B. `de`, `en` oder `None` (Auto)
- `input_topic`: typischerweise `/g1/mics/pcm16`
- `output_topic`: typischerweise `callboy/input_text`
- `silence_threshold`, `silence_duration`, `min_speech_duration`: VAD Tuning
- `wakeword`: optional (z. B. `Robert`) – nur wenn Wakeword erkannt wird, wird Text publiziert
- `log_rms`: `true` loggt RMS, um `silence_threshold` zu kalibrieren

#### `[riva]` (optional)

Der Code unterstützt zusätzliche Riva-Parameter (Server, Sprache, VAD-Gate, Wakeword, etc.). Im Repo ist nicht zwingend eine `[riva]`-Sektion vorhanden; bei Bedarf ergänzen.

## Starten

### 1) Quickstart per Launch

```bash
export CALLBOY_CONFIG="$PWD/callboy.conf"
cd ros2_ws
source install/setup.bash
ros2 launch callboy callboy.launch.py
```

Die Launch-Datei startet standardmäßig:

- `callboy_udp_audio_topic` (UDP → `/g1/mics/pcm16`)
- `callboy_whisper_asr` (ASR → `callboy/input_text`)
- `callboy_ollama_planner` (Text → JSON)
- `callboy_sdk2_executor` (JSON → SDK2 CLI)

`callboy_riva_asr` und `callboy_input_text` sind im Launch aktuell auskommentiert.

### 2) Text-Eingabe ohne ASR

In einem Terminal Nodes starten (oder Launch anpassen) und Text publizieren:

```bash
cd ros2_ws
source install/setup.bash
ros2 run callboy callboy_input_text
```

Oder per Param einmalig:

```bash
ros2 run callboy callboy_input_text --ros-args -p text:="wave hand" -p once:=true
```

### 3) Ollama vorbereiten

Ollama muss laufen und das Modell vorhanden sein:

```bash
ollama serve
ollama list
```

`callboy_ollama_planner` ruft `POST {ollama_url}/api/generate` auf.

## Nodes im Detail

### `callboy_udp_audio_topic` (UDP → ROS2 Audio)

Publiziert rohen PCM-Byte-Stream als `std_msgs/UInt8MultiArray` auf eine Topic (Default: `/g1/mics/pcm16`).

Wichtige Parameter:

- `mcast_group` (Default: `239.168.123.161`)
- `port` (Default: `5555`)
- `local_ip` (Default: `192.168.123.164`) – Interface-IP für IGMP Join
- `topic` (Default: `/g1/mics/pcm16`)
- `header_skip_bytes` (Default: `0`) – falls UDP Payload einen Header hat
- `channels` (Default: `1`), `sample_width_bytes` (Default: `2`) – Metadata/Layout
- `best_effort` (Default: `true`) und `qos_depth`

### `callboy_whisper_asr` (Whisper ASR)

Abonniert `whisper.input_topic` (Default: `/g1/mics/pcm16`) und publiziert erkannten Text auf `whisper.output_topic` (Default: `callboy/input_text`).

Eigenschaften:

- RMS-basierte VAD (Silence-Threshold + Silence-Duration), danach Transkription.
- Optionales Wakeword: ohne Wakeword wird **nichts** an `callboy/input_text` publiziert.
- Modell: `faster-whisper` (`WhisperModel`) – bei GPU-Fehler Fallback auf CPU `int8`.

### `callboy_riva_asr` (optional, Streaming)

Abonniert Audio-Topic und streamt an einen Riva ASR Server. Publiziert finale Transkripte auf `output_topic`.

Eigenschaften:

- Queue/Chunking (`chunk_ms`) und optionales RMS Noise-Gate (`vad_threshold`).
- Optionales Wakeword: publiziert nur Text **nach** dem Wakeword.
- Benötigt `riva.client` im Python Environment.

### `callboy_ollama_planner` (Text → JSON)

Abonniert `callboy/input_text` und publiziert `callboy/json`.

Wichtig:

- Prompt aus `planner.prompt_file` (Default-Fallback: `prompts/default.txt`).
- Ollama-Aufruf: `POST /api/generate` (non-streaming).
- Sicherheits-/Normalisierungslogik:
	- Es wird auf eine kleine **Allowlist** reduziert: `set_velocity`, `shake_hand`, `wave_hand`, `wave_hand_with_turn`.
	- Für `set_velocity` ist ein Param zwingend.
	- Nach jedem `set_velocity` wird automatisch `stop_move` ans Plan-Ende angehängt.

Ausgabeformat ist ein JSON-Objekt wie:

```json
{"commands": [{"name": "set_velocity", "param": "0.3 0 0 2.0"}, {"name": "stop_move"}]}
```

### `callboy_sdk2_executor` (JSON → SDK2 CLI)

Abonniert `callboy/json`, validiert gegen `SUPPORTED_COMMANDS` und führt Kommandos sequenziell aus.

Wichtige Parameter:

- `sdk2_cli_path` (aus Config) – muss existieren
- `network_interface`
- `dry_run` – führt keine Subprocesses aus (liefert `DRY_RUN`)
- `wait_for_velocity_duration` – wenn `set_velocity` direkt von `stop_move` gefolgt wird, wartet der Executor (basierend auf Dauer im Param), damit Bewegung sichtbar ist

## Prompts

Die Prompt-Templates liegen in `ros2_ws/src/callboy/prompts/`.

- `default.txt`: strikter Planner (Deutsch+Englisch), Defaults und Mappings für Bewegung
- `llama-3.1.txt`: alternative, kürzere Regeln inkl. Grad→Zeit Heuristik

## DDS / Transport Hinweise (optional)

Für lokale Tests (nur Loopback) ist ein CycloneDDS Profil vorhanden:

- `ros2_ws/cyclonedds_lo.xml` (Interface `lo`, kein Multicast)

Für FastDDS ohne Shared Memory ist ein Profil vorhanden:

- `ros2_ws/fastdds_no_shm.xml` (UDP Transport only)

Beispiele:

```bash
# CycloneDDS
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file://$PWD/ros2_ws/cyclonedds_lo.xml

# FastDDS
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE=$PWD/ros2_ws/fastdds_no_shm.xml
```

## Tools / Debug

### Audio mitschneiden

`ros2_ws/record_audio.py` subscribed `/g1/mics/pcm16` und schreibt `test_audio.wav` (16kHz, mono, 16-bit) nach ~30 Sekunden.

Beispiel:

```bash
cd ros2_ws
source install/setup.bash
python3 record_audio.py
```

### Topics anschauen

```bash
ros2 topic list
ros2 topic echo /g1/mics/pcm16
ros2 topic echo callboy/input_text
ros2 topic echo callboy/json
```

## Troubleshooting

- **Config nicht gefunden**: setze `CALLBOY_CONFIG` auf das Repo-`callboy.conf`.
- **Planner meldet "requests is missing"**: `python3-requests` installieren oder `pip install requests`.
- **Whisper findet keine Publisher**: `callboy_udp_audio_topic` muss laufen und auf die richtige Topic publizieren (`/g1/mics/pcm16`).
- **VAD triggert nicht / zu oft**: setze in `callboy.conf` `whisper.log_rms=true` und passe `whisper.silence_threshold` an.
- **Executor führt nichts aus**: prüfe `sdk2.cli_path` und ob `sdk2.dry_run=true` gesetzt ist.
- **Ollama Timeout**: `callboy_ollama_planner` Parameter `timeout_s` erhöhen.

