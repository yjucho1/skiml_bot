from skiml_bot.server_status import ServerStatus, SlurmNode, StorageVolume, is_server_status_request


def test_server_status_request_requires_bot_mention() -> None:
    assert is_server_status_request("<@U123ABC> 연구실서버 상태 알려줘")
    assert is_server_status_request("<@U123ABC> 연구실 서버 상태 일려줘")
    assert is_server_status_request("<@U123ABC> slurm 노드 상태 확인해줘")
    assert not is_server_status_request("연구실서버 상태 알려줘")


def test_server_status_request_does_not_match_unrelated_server_question() -> None:
    assert not is_server_status_request("<@U123ABC> 서버 사용법 알려줘")


def test_server_status_formats_only_drain_family_as_warning() -> None:
    status = ServerStatus(
        nodes=(
            SlurmNode("master", "mixed"),
            SlurmNode("n01", "draining", "Kill task failed"),
            SlurmNode("n02", "drained", "maintenance"),
        )
    )

    message = status.for_slack()

    assert "Master SSH* — 🟢 접속 정상" in message
    assert "*전체 노드* — 3개" in message
    assert "*DRAIN 계열* — 2개" in message
    assert "`n01` — draining — Kill task failed" in message
    assert "`n02` — drained — maintenance" in message
    assert "`master`" not in message


def test_server_status_reports_no_drained_nodes() -> None:
    status = ServerStatus(
        nodes=tuple(
            SlurmNode(name, "mixed") for name in ("master", "n01", "n02", "n03", "n04", "n05")
        )
    )

    message = status.for_slack()

    assert "*전체 노드* — 6개" in message
    assert "*DRAIN 계열* — 0개" in message
    assert "DRAIN 상태인 노드가 없습니다." in message


def test_server_status_reports_remaining_storage_and_warns_at_ninety_percent() -> None:
    status = ServerStatus(
        nodes=(SlurmNode("master", "mixed"),),
        storage=(
            StorageVolume("/dev/sda1", "1.8T", "845G", "825G", 51, "/home"),
            StorageVolume("storage:/data", "10T", "9.2T", "800G", 92, "/data"),
        ),
    )

    message = status.for_slack()

    assert "*스토리지 사용 공간 - 상위 3개*" in message
    assert "🟢 `/home` — 825G 남음 / 1.8T (51% 사용)" in message
    assert "🔴 `/data` — 800G 남음 / 10T (92% 사용)" in message
    assert status.low_storage_volumes == (status.storage[1],)


def test_server_status_displays_only_three_volumes_but_checks_all_for_low_space() -> None:
    status = ServerStatus(
        nodes=(SlurmNode("master", "mixed"),),
        storage=(
            StorageVolume("n03:/data5", "7T", "2T", "4.7T", 29, "/data5"),
            StorageVolume("n03:/data4", "7T", "2.8T", "3.9T", 42, "/data4"),
            StorageVolume("n03:/data8", "7T", "6.5T", "500G", 93, "/data8"),
            StorageVolume("n03:/data7", "7T", "2.4T", "4.3T", 37, "/data7"),
        ),
    )

    message = status.for_slack()

    assert "`/data4`" in message
    assert "`/data8`" in message
    assert "`/data7`" in message
    assert "`/data5`" not in message
    assert status.low_storage_volumes == (status.storage[2],)
