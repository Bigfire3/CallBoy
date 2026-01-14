from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Command:
    name: str
    param: Optional[str] = None


@dataclass(frozen=True)
class Plan:
    commands: List[Command]
    unavailable: List[str]


@dataclass(frozen=True)
class ExecutionResult:
    command: Command
    returncode: int
    stdout: str
    stderr: str


def plan_from_json_dict(obj: Dict[str, Any]) -> Plan:
    commands_raw = obj.get("commands")
    unavailable_raw = obj.get("unavailable", [])

    if not isinstance(commands_raw, list):
        raise ValueError("plan.commands must be a list")

    commands: List[Command] = []
    for item in commands_raw:
        if not isinstance(item, dict):
            raise ValueError("each plan.commands item must be an object")
        name = item.get("name")
        param = item.get("param")
        if not isinstance(name, str) or name.strip() == "":
            raise ValueError("command.name must be a non-empty string")
        if param is not None and not isinstance(param, str):
            raise ValueError("command.param must be a string when present")
        commands.append(Command(name=name, param=param))

    if not isinstance(unavailable_raw, list) or not all(
        isinstance(x, str) for x in unavailable_raw
    ):
        raise ValueError("plan.unavailable must be a list of strings")

    return Plan(commands=commands, unavailable=list(unavailable_raw))
