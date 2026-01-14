from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass as _dataclass

from .command_schema import Command, ExecutionResult, Plan


def dataclass(*args: object, **kwargs: object):  # type: ignore[no-redef]
    if sys.version_info < (3, 10):
        kwargs.pop("slots", None)
    return _dataclass(*args, **kwargs)


@dataclass(frozen=True, slots=True)
class ExecutorConfig:
    """Configuration for invoking the SDK2 CLI."""

    sdk2_cli_path: str
    network_interface: str = "lo"
    timeout_s: float = 30.0


def execute_plan(plan: Plan, *, cfg: ExecutorConfig, dry_run: bool = False) -> list[ExecutionResult]:
    """Execute the given plan sequentially."""

    results: list[ExecutionResult] = []
    commands = list(plan.commands)
    for idx, command in enumerate(commands):
        result = _execute_one(command, cfg=cfg, dry_run=dry_run)
        results.append(result)
        if result.returncode != 0:
            break

        # Common safety pattern: set_velocity with finite duration followed by stop_move.
        # The SDK2 CLI example's SetVelocity call is non-blocking, so without a delay the
        # immediate stop_move may cancel motion before it becomes visible.
        if (
            command.name == "set_velocity"
            and (idx + 1) < len(commands)
            and commands[idx + 1].name == "stop_move"
        ):
            duration_s = _parse_velocity_duration_s(command.param)
            if duration_s is not None and duration_s > 0:
                time.sleep(duration_s)
    return results


def _parse_velocity_duration_s(param: str | None) -> float | None:
    if param is None:
        return None
    parts = param.strip().split()
    if len(parts) == 4:
        try:
            return float(parts[3])
        except Exception:
            return None
    if len(parts) == 3:
        # SDK2 example uses 1 second by default when duration omitted.
        return 1.0
    return None


def _execute_one(command: Command, *, cfg: ExecutorConfig, dry_run: bool) -> ExecutionResult:
    args = [
        cfg.sdk2_cli_path,
        f"--network_interface={cfg.network_interface}",
    ]

    if command.param is None or command.param == "":
        args.append(f"--{command.name}")
    else:
        args.append(f"--{command.name}={command.param}")

    if dry_run:
        return ExecutionResult(command=command, returncode=0, stdout="DRY_RUN", stderr="")

    completed = subprocess.run(
        args,
        text=True,
        capture_output=True,
        timeout=cfg.timeout_s,
        check=False,
    )
    return ExecutionResult(
        command=command,
        returncode=int(completed.returncode),
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
