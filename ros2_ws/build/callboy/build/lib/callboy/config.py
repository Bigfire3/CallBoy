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
class CallboyConfig:
    ollama: OllamaConfig
    sdk2: Sdk2Config


def _get_str(parser: configparser.ConfigParser, section: str, option: str, fallback: str) -> str:
    if not parser.has_section(section):
        return fallback
    try:
        return parser.get(section, option, fallback=fallback)
    except Exception:
        return fallback


def _get_bool(parser: configparser.ConfigParser, section: str, option: str, fallback: bool) -> bool:
    if not parser.has_section(section):
        return fallback
    try:
        return parser.getboolean(section, option, fallback=fallback)
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

    sdk2 = Sdk2Config(
        cli_path=_get_str(parser, "sdk2", "cli_path", Sdk2Config.cli_path),
        network_interface=_get_str(parser, "sdk2", "network_interface", Sdk2Config.network_interface),
        dry_run=_get_bool(parser, "sdk2", "dry_run", Sdk2Config.dry_run),
    )

    return CallboyConfig(ollama=ollama, sdk2=sdk2)
