import subprocess

import pytest

from skiml_bot.adapters.ssh_slurm import (
    SlurmCommandError,
    SSHConnectionError,
    SSHSlurmStatusSource,
    parse_df,
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
        return subprocess.CompletedProcess(
            argv,
            0,
            "master|mixed|none\nn01|idle|none\n"
            "__SKIML_STORAGE__\n"
            "Filesystem Size Used Avail Use% Mounted on\n"
            "/dev/root 200G 120G 80G 60% /\n"
            "/dev/sda1 1.8T 845G 825G 51% /home\n"
            "storage:/data 10T 7T 3T 70% /data\n",
            "",
        )

    source = SSHSlurmStatusSource(
        "bot-user@login.example.edu",
        identity_file="/run/secrets/slurm-monitor",
        known_hosts_file="/run/secrets/known_hosts",
        timeout_seconds=7,
        runner=fake_runner,
    )

    status = source.fetch()

    assert len(status.nodes) == 2
    assert [(volume.mount_point, volume.available) for volume in status.storage] == [
        ("/home", "825G"),
        ("/data", "3T"),
    ]
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
        "sinfo -N -h -o '%N|%T|%E'; printf '\\n__SKIML_STORAGE__\\n'; "
        "df -hP -x tmpfs -x devtmpfs -x squashfs",
    ]
    assert timeout == 9


def test_parse_df_reads_human_readable_capacity() -> None:
    volumes = parse_df(
        "Filesystem Size Used Avail Use% Mounted on\n"
        "/dev/sda1 200G 120G 80G 60% /\n"
        "/dev/sda2 1.8T 845G 825G 51% /home\n"
        "storage:/data 10T 9.2T 800G 92% /data\n"
        "storage:/data2 7T 2T 4.7T 29% /data2\n"
        "storage:/data3 7T 5.2T 1.4T 79% /data3\n"
        "storage:/archive 20T 5T 15T 25% /archive\n"
    )

    assert [(volume.mount_point, volume.available, volume.use_percent) for volume in volumes] == [
        ("/home", "825G", 51),
        ("/data", "800G", 92),
        ("/data2", "4.7T", 29),
        ("/data3", "1.4T", 79),
    ]


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
