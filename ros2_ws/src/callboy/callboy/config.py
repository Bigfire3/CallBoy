from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class OllamaConfig:
    url: str = "http://localhost:11434"
    model: str = "qwen2.5:3b-instruct"
    timeout_s: float = 60.0


@dataclass(frozen=True)
class Sdk2Config:
    cli_path: str = "/home/unitree/unitree_sdk2/build/bin/g1_loco_client"
    network_interface: str = "eth0"
    timeout_s: float = 30.0
    dry_run: bool = False
    wait_for_velocity_duration: bool = True


@dataclass(frozen=True)
class CallboyConfig:
    ollama: OllamaConfig
    sdk2: Sdk2Config


def default_config_path() -> str:
    return os.environ.get("CALLBOY_CONFIG", "/home/unitree/callboy/callboy.conf")


def load_config(path: Optional[str] = None) -> CallboyConfig:
    cfg_path = path or default_config_path()

    parser = configparser.ConfigParser()
    read = parser.read(cfg_path)
    if not read:
        # Missing config is not fatal: fall back to defaults.
        return CallboyConfig(ollama=OllamaConfig(), sdk2=Sdk2Config())

    ollama = OllamaConfig(
        url=parser.get("ollama", "url", fallback=OllamaConfig.url),
        model=parser.get("ollama", "model", fallback=OllamaConfig.model),
        timeout_s=parser.getfloat("ollama", "timeout_s", fallback=OllamaConfig.timeout_s),
    )

    sdk2 = Sdk2Config(
        cli_path=parser.get("sdk2", "cli_path", fallback=Sdk2Config.cli_path),
        network_interface=parser.get("sdk2", "network_interface", fallback=Sdk2Config.network_interface),
        timeout_s=parser.getfloat("sdk2", "timeout_s", fallback=Sdk2Config.timeout_s),
        dry_run=parser.getboolean("sdk2", "dry_run", fallback=Sdk2Config.dry_run),
        wait_for_velocity_duration=parser.getboolean(
            "sdk2", "wait_for_velocity_duration", fallback=Sdk2Config.wait_for_velocity_duration
        ),
    )

    return CallboyConfig(ollama=ollama, sdk2=sdk2)
