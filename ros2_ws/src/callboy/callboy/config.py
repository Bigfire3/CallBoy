from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class OllamaConfig:
    url: str = "http://localhost:11434"
    model: str = "qwen2.5:3b-instruct"


@dataclass(frozen=True)
class Sdk2Config:
    cli_path: str = "/home/unitree/unitree_sdk2/build/bin/g1_loco_client"
    network_interface: str = "eth0"
    dry_run: bool = False


@dataclass(frozen=True)
class RivaConfig:
    server: str = "localhost:50051"
    language_code: str = "de-DE"
    sample_rate_hz: int = 16000
    channels: int = 1
    interim_results: bool = True
    print_interim: bool = True
    enable_automatic_punctuation: bool = False
    input_topic: str = "/g1/mics/pcm16"
    output_topic: str = "callboy/input_text"
    vad_threshold: float = 0.005
    wakeword: str = ""
    log_rms: bool = False


@dataclass(frozen=True)
class WhisperConfig:
    model_size: str = "small"
    device: str = "cuda"
    compute_type: str = "int8"
    language: str = "de"
    input_topic: str = "/g1/mics/pcm16"
    output_topic: str = "callboy/input_text"
    silence_threshold: int = 500
    silence_duration: float = 1.0
    min_speech_duration: float = 0.5
    log_rms: bool = False


@dataclass(frozen=True)
class PlannerConfig:
    # Path to a prompt file used by the LLM planner.
    # May be absolute or relative (see nodes for resolution rules).
    prompt_file: str = ""


@dataclass(frozen=True)
class CallboyConfig:
    ollama: OllamaConfig
    planner: PlannerConfig
    sdk2: Sdk2Config
    riva: RivaConfig
    whisper: WhisperConfig


def _get_str(parser: configparser.ConfigParser, section: str, option: str, fallback: str) -> str:
    if not parser.has_section(section):
        return fallback
    try:
        return parser.get(section, option, fallback=fallback)
    except Exception:
        return fallback


def _get_int(parser: configparser.ConfigParser, section: str, option: str, fallback: int) -> int:
    if not parser.has_section(section):
        return fallback
    try:
        return parser.getint(section, option, fallback=fallback)
    except Exception:
        return fallback


def _get_bool(parser: configparser.ConfigParser, section: str, option: str, fallback: bool) -> bool:
    if not parser.has_section(section):
        return fallback
    try:
        return parser.getboolean(section, option, fallback=fallback)
    except Exception:
        return fallback


def _get_float(parser: configparser.ConfigParser, section: str, option: str, fallback: float) -> float:
    if not parser.has_section(section):
        return fallback
    try:
        return parser.getfloat(section, option, fallback=fallback)
    except Exception:
        return fallback


def default_config_path() -> str:
    return os.environ.get("CALLBOY_CONFIG", "/home/unitree/callboy/callboy.conf")


def load_config(path: Optional[str] = None) -> CallboyConfig:
    cfg_path = path or default_config_path()

    if not os.path.exists(cfg_path):
        raise FileNotFoundError(f"callboy.conf not found at: {cfg_path}")

    parser = configparser.ConfigParser()
    read = parser.read(cfg_path)
    if not read:
        # Exists, but could not be read (permissions/encoding/etc.).
        raise FileNotFoundError(f"callboy.conf exists but could not be read: {cfg_path}")

    ollama = OllamaConfig(
        url=_get_str(parser, "ollama", "url", OllamaConfig.url),
        model=_get_str(parser, "ollama", "model", OllamaConfig.model),
    )

    planner = PlannerConfig(
        prompt_file=_get_str(parser, "planner", "prompt_file", PlannerConfig.prompt_file),
    )

    sdk2 = Sdk2Config(
        cli_path=_get_str(parser, "sdk2", "cli_path", Sdk2Config.cli_path),
        network_interface=_get_str(parser, "sdk2", "network_interface", Sdk2Config.network_interface),
        dry_run=_get_bool(parser, "sdk2", "dry_run", Sdk2Config.dry_run),
    )

    riva = RivaConfig(
        server=_get_str(parser, "riva", "server", RivaConfig.server),
        language_code=_get_str(parser, "riva", "language_code", RivaConfig.language_code),
        sample_rate_hz=_get_int(parser, "riva", "sample_rate_hz", RivaConfig.sample_rate_hz),
        channels=_get_int(parser, "riva", "channels", RivaConfig.channels),
        interim_results=_get_bool(parser, "riva", "interim_results", RivaConfig.interim_results),
        print_interim=_get_bool(parser, "riva", "print_interim", RivaConfig.print_interim),
        enable_automatic_punctuation=_get_bool(parser, "riva", "enable_automatic_punctuation", RivaConfig.enable_automatic_punctuation),
        input_topic=_get_str(parser, "riva", "input_topic", RivaConfig.input_topic),
        output_topic=_get_str(parser, "riva", "output_topic", RivaConfig.output_topic),
        vad_threshold=_get_float(parser, "riva", "vad_threshold", RivaConfig.vad_threshold),
        wakeword=_get_str(parser, "riva", "wakeword", RivaConfig.wakeword),
        log_rms=_get_bool(parser, "riva", "log_rms", RivaConfig.log_rms),
    )

    whisper = WhisperConfig(
        model_size=_get_str(parser, "whisper", "model_size", WhisperConfig.model_size),
        device=_get_str(parser, "whisper", "device", WhisperConfig.device),
        compute_type=_get_str(parser, "whisper", "compute_type", WhisperConfig.compute_type),
        language=_get_str(parser, "whisper", "language", WhisperConfig.language),
        input_topic=_get_str(parser, "whisper", "input_topic", WhisperConfig.input_topic),
        output_topic=_get_str(parser, "whisper", "output_topic", WhisperConfig.output_topic),
        silence_threshold=_get_int(parser, "whisper", "silence_threshold", WhisperConfig.silence_threshold),
        silence_duration=_get_float(parser, "whisper", "silence_duration", WhisperConfig.silence_duration),
        min_speech_duration=_get_float(parser, "whisper", "min_speech_duration", WhisperConfig.min_speech_duration),
        log_rms=_get_bool(parser, "whisper", "log_rms", WhisperConfig.log_rms),
    )

    return CallboyConfig(ollama=ollama, planner=planner, sdk2=sdk2, riva=riva, whisper=whisper)
