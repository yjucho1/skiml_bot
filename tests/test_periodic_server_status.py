from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from skiml_bot.periodic_server_status import PeriodicServerStatusPublisher
from skiml_bot.server_status import ServerStatus, SlurmNode


@dataclass
class FakeStatusSource:
    status: ServerStatus

    def fetch(self) -> ServerStatus:
        return self.status


@dataclass
class FlakyStatusSource:
    results: list[ServerStatus | Exception]

    def fetch(self) -> ServerStatus:
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


@dataclass
class FakeChannel:
    messages: list[tuple[str, str]] = field(default_factory=list)

    def post_channel(self, channel_id: str, text: str) -> None:
        self.messages.append((channel_id, text))


@dataclass
class FakeStopSignal:
    results: list[bool]
    waits: list[float] = field(default_factory=list)

    def wait(self, timeout: float) -> bool:
        self.waits.append(timeout)
        return self.results.pop(0)


def test_periodic_publisher_posts_current_status_to_configured_channel() -> None:
    channel = FakeChannel()
    publisher = PeriodicServerStatusPublisher(
        FakeStatusSource(ServerStatus((SlurmNode("master", "mixed"),))),
        channel,
        channel_id="C0123456789",
        schedule_timezone=ZoneInfo("Asia/Seoul"),
    )

    publisher.publish()

    assert channel.messages == [
        (
            "C0123456789",
            "*[연구실 서버 상태]*\n"
            "*Master SSH* — 🟢 접속 정상\n"
            "*전체 노드* — 1개\n"
            "*DRAIN 계열* — 0개\n"
            "🟢 DRAIN 상태인 노드가 없습니다.",
        )
    ]


def test_periodic_publisher_waits_until_next_scheduled_hour() -> None:
    channel = FakeChannel()
    times = iter(
        (
            datetime(2026, 9, 1, 7, 45, tzinfo=timezone(timedelta(hours=9))),
            datetime(2026, 9, 1, 8, 0, tzinfo=timezone(timedelta(hours=9))),
        )
    )
    publisher = PeriodicServerStatusPublisher(
        FakeStatusSource(ServerStatus((SlurmNode("master", "mixed"),))),
        channel,
        channel_id="C0123456789",
        schedule_timezone=ZoneInfo("Asia/Seoul"),
        clock=lambda: next(times),
    )
    stop = FakeStopSignal([False, True])

    publisher.run(stop)

    assert stop.waits == [900, 7200]
    assert len(channel.messages) == 1


def test_periodic_publisher_waits_until_next_morning_after_last_post() -> None:
    publisher = PeriodicServerStatusPublisher(
        FakeStatusSource(ServerStatus((SlurmNode("master", "mixed"),))),
        FakeChannel(),
        channel_id="C0123456789",
        schedule_timezone=ZoneInfo("Asia/Seoul"),
    )

    delay = publisher._seconds_until_next_publish(
        datetime(2026, 9, 1, 20, 0, tzinfo=timezone(timedelta(hours=9)))
    )

    assert delay == 12 * 60 * 60


def test_periodic_publisher_converts_clock_to_schedule_timezone() -> None:
    publisher = PeriodicServerStatusPublisher(
        FakeStatusSource(ServerStatus((SlurmNode("master", "mixed"),))),
        FakeChannel(),
        channel_id="C0123456789",
        schedule_timezone=ZoneInfo("Asia/Seoul"),
    )

    delay = publisher._seconds_until_next_publish(
        datetime(2026, 8, 31, 22, 30, tzinfo=timezone.utc)
    )

    assert delay == 30 * 60


def test_periodic_publisher_reports_failure_and_continues_at_next_scheduled_hour() -> None:
    timezone_kst = timezone(timedelta(hours=9))
    times = iter(
        (
            datetime(2026, 9, 1, 7, 59, tzinfo=timezone_kst),
            datetime(2026, 9, 1, 8, 0, tzinfo=timezone_kst),
            datetime(2026, 9, 1, 10, 0, tzinfo=timezone_kst),
        )
    )
    channel = FakeChannel()
    publisher = PeriodicServerStatusPublisher(
        FlakyStatusSource(
            [
                RuntimeError("temporary SSH failure"),
                ServerStatus((SlurmNode("master", "mixed"),)),
            ]
        ),
        channel,
        channel_id="C0123456789",
        schedule_timezone=ZoneInfo("Asia/Seoul"),
        clock=lambda: next(times),
    )

    publisher.run(FakeStopSignal([False, False, True]))

    assert channel.messages[0] == (
        "C0123456789",
        "🔴 *[연구실 서버 상태]*\nSSH 또는 `sinfo` 조회에 실패했습니다.",
    )
    assert "*전체 노드* — 1개" in channel.messages[1][1]
