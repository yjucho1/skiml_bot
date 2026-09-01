import subprocess

import pytest

from skiml_bot.adapters.ssh_slurm import (
    SlurmCommandError,
    SSHConnectionError,
    SSHSlurmStatusSource,
    parse_sinfo,
)


def test_parse_sinfo_handles_slurm_19_output_and_deduplicates_nodes() -> None:
    nodes = parse_sinfo(
        "master|mixed|none\nn01|idle|none\nn01|drained|maintenance\nn02|drng|Kill task failed\n"
    )

    assert [(node.name, node.state, node.reason) for node in nodes] == [
        ("master", "mixed", None),
        ("n01", "drained", "maintenance"),
        ("n02", "drng", "Kill task failed"),
    ]


def test_fetch_uses_batch_ssh_and_fixed_sinfo_command() -> None:
    calls: list[tuple[list[str], float]] = []

    def fake_runner(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append((argv, timeout))
        return subprocess.CompletedProcess(argv, 0, "master|mixed|none\nn01|idle|none\n", "")

    source = SSHSlurmStatusSource(
        "bot-user@login.example.edu",
        identity_file="/run/secrets/slurm-monitor",
        known_hosts_file="/run/secrets/known_hosts",
        timeout_seconds=7,
        runner=fake_runner,
    )

    status = source.fetch()

    assert len(status.nodes) == 2
    argv, timeout = calls[0]
    assert argv == [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=7",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "UserKnownHostsFile=/run/secrets/known_hosts",
        "-i",
        "/run/secrets/slurm-monitor",
        "bot-user@login.example.edu",
        "sinfo -N -h -o '%N|%T|%E'",
    ]
    assert timeout == 9


def test_fetch_distinguishes_ssh_failure_from_slurm_failure() -> None:
    def ssh_failure(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 255, "", "Permission denied (publickey).")

    with pytest.raises(SSHConnectionError, match="Permission denied"):
        SSHSlurmStatusSource("user@master", runner=ssh_failure).fetch()

    def slurm_failure(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 1, "", "sinfo: error: slurm_load_partitions")

    with pytest.raises(SlurmCommandError, match="slurm_load_partitions"):
        SSHSlurmStatusSource("user@master", runner=slurm_failure).fetch()


def test_fetch_retries_transient_ssh_reset_before_succeeding() -> None:
    results = [
        subprocess.CompletedProcess(
            ["ssh"],
            255,
            "",
            "kex_exchange_identification: read: Connection reset by peer",
        ),
        subprocess.CompletedProcess(["ssh"], 0, "master|mixed|none\n", ""),
    ]
    delays: list[float] = []

    def flaky_runner(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        return results.pop(0)

    source = SSHSlurmStatusSource(
        "user@master",
        runner=flaky_runner,
        sleeper=delays.append,
    )

    status = source.fetch()

    assert len(status.nodes) == 1
    assert delays == [2.0]


def test_fetch_reports_transient_ssh_failure_after_three_attempts() -> None:
    attempts = 0
    delays: list[float] = []

    def reset_connection(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        attempts += 1
        return subprocess.CompletedProcess(argv, 255, "", "Connection reset by peer")

    source = SSHSlurmStatusSource(
        "user@master",
        runner=reset_connection,
        sleeper=delays.append,
    )

    with pytest.raises(SSHConnectionError, match="Connection reset"):
        source.fetch()

    assert attempts == 3
    assert delays == [2.0, 2.0]
