from __future__ import annotations

import subprocess
import sys
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
    for command in plan.commands:
        result = _execute_one(command, cfg=cfg, dry_run=dry_run)
        results.append(result)
        if result.returncode != 0:
            break
    return results


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
