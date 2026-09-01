"""Read Slurm node state through a non-interactive SSH connection."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable

from skiml_bot.server_status import ServerStatus, SlurmNode

SINFO_COMMAND = "sinfo -N -h -o '%N|%T|%E'"
Runner = Callable[[list[str], float], subprocess.CompletedProcess[str]]
Sleeper = Callable[[float], None]
MAX_SSH_ATTEMPTS = 3
SSH_RETRY_DELAY_SECONDS = 2.0


class SSHConnectionError(RuntimeError):
    """The Slurm master could not be reached or authenticated."""


class SlurmCommandError(RuntimeError):
    """SSH worked, but the remote Slurm query failed."""


def _run_command(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class SSHSlurmStatusSource:
    def __init__(
        self,
        target: str,
        *,
        identity_file: str | None = None,
        known_hosts_file: str | None = None,
        timeout_seconds: int = 10,
        runner: Runner = _run_command,
        sleeper: Sleeper = time.sleep,
    ) -> None:
        if not target or target.startswith("-") or any(character.isspace() for character in target):
            raise ValueError("SLURM_SSH_TARGET must be a host or user@host without whitespace")
        if timeout_seconds <= 0:
            raise ValueError("SLURM_SSH_TIMEOUT_SECONDS must be positive")
        self._target = target
        self._identity_file = identity_file
        self._known_hosts_file = known_hosts_file
        self._timeout_seconds = timeout_seconds
        self._runner = runner
        self._sleeper = sleeper

    def fetch(self) -> ServerStatus:
        argv = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={self._timeout_seconds}",
            "-o",
            "StrictHostKeyChecking=yes",
        ]
        if self._known_hosts_file:
            argv.extend(["-o", f"UserKnownHostsFile={self._known_hosts_file}"])
        if self._identity_file:
            argv.extend(["-i", self._identity_file])
        argv.extend([self._target, SINFO_COMMAND])

        result = self._run_ssh_with_retries(argv)

        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        if result.returncode == 255:
            raise SSHConnectionError(detail)
        if result.returncode != 0:
            raise SlurmCommandError(detail)
        nodes = parse_sinfo(result.stdout)
        if not nodes:
            raise SlurmCommandError("sinfo returned no nodes")
        return ServerStatus(nodes)

    def _run_ssh_with_retries(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        for attempt in range(1, MAX_SSH_ATTEMPTS + 1):
            try:
                result = self._runner(argv, float(self._timeout_seconds + 2))
            except subprocess.TimeoutExpired as error:
                if attempt == MAX_SSH_ATTEMPTS:
                    raise SSHConnectionError(str(error)) from error
                self._sleeper(SSH_RETRY_DELAY_SECONDS)
                continue
            except OSError as error:
                raise SSHConnectionError(str(error)) from error

            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            if (
                result.returncode != 255
                or not _is_retryable_ssh_error(detail)
                or attempt == MAX_SSH_ATTEMPTS
            ):
                return result
            self._sleeper(SSH_RETRY_DELAY_SECONDS)
        raise AssertionError("SSH retry loop ended unexpectedly")


def _is_retryable_ssh_error(detail: str) -> bool:
    normalized = detail.casefold()
    return any(
        marker in normalized
        for marker in (
            "connection reset",
            "kex_exchange_identification",
            "connection timed out",
            "operation timed out",
        )
    )


def parse_sinfo(output: str) -> tuple[SlurmNode, ...]:
    """Parse pipe-delimited sinfo output, preferring DRAIN rows for duplicates."""
    by_name: dict[str, SlurmNode] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 2)
        if len(parts) != 3:
            raise SlurmCommandError(f"Unexpected sinfo output: {line}")
        name, state, raw_reason = (part.strip() for part in parts)
        if not name or not state:
            raise SlurmCommandError(f"Unexpected sinfo output: {line}")
        reason = None if raw_reason.casefold() in {"", "none", "(null)", "n/a"} else raw_reason
        node = SlurmNode(name=name, state=state, reason=reason)
        previous = by_name.get(name)
        if previous is None or (node.is_drain and not previous.is_drain):
            by_name[name] = node
    return tuple(by_name.values())
