"""Periodic publication of the current Slurm server status."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, time, timedelta, timezone, tzinfo
from typing import Protocol

from skiml_bot.adapters.ssh_slurm import SSHConnectionError
from skiml_bot.server_status import ServerStatus

LOGGER = logging.getLogger(__name__)
FAILURE_MESSAGE = "🔴 *[연구실 서버 상태]*\nSSH 또는 `sinfo` 조회에 실패했습니다."
STATUS_PUBLISH_HOURS = (8, 12, 16, 20)
CONNECTION_FAILURE_REASON = "접속 안됨"
DRAIN_NODE_REASON = "drain 노드 발생"


class StatusSource(Protocol):
    def fetch(self) -> ServerStatus: ...


class ChannelPublisher(Protocol):
    def post_channel(self, channel_id: str, text: str) -> None: ...


class StopSignal(Protocol):
    def wait(self, timeout: float) -> bool: ...


class AlertWorkflow(Protocol):
    def trigger(self, reason: str) -> None: ...


class PeriodicServerStatusPublisher:
    def __init__(
        self,
        source: StatusSource,
        channel: ChannelPublisher,
        *,
        channel_id: str,
        schedule_timezone: tzinfo,
        publish_hours: tuple[int, ...] = STATUS_PUBLISH_HOURS,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        alert_workflow: AlertWorkflow | None = None,
    ) -> None:
        if not channel_id:
            raise ValueError("Periodic server status channel ID must not be empty")
        if not publish_hours or any(hour < 0 or hour > 23 for hour in publish_hours):
            raise ValueError("Periodic server status hours must be between 0 and 23")
        if len(set(publish_hours)) != len(publish_hours):
            raise ValueError("Periodic server status hours must not contain duplicates")
        self._source = source
        self._channel = channel
        self._channel_id = channel_id
        self._schedule_timezone = schedule_timezone
        self._publish_hours = tuple(sorted(publish_hours))
        self._clock = clock
        self._alert_workflow = alert_workflow

    def publish(self) -> None:
        status = self._source.fetch()
        if status.drain_nodes:
            self._trigger_alert(DRAIN_NODE_REASON)
        self._channel.post_channel(self._channel_id, status.for_slack())

    def run(self, stop: StopSignal) -> None:
        while True:
            delay = self._seconds_until_next_publish(self._clock())
            if stop.wait(delay):
                return
            try:
                self.publish()
            except SSHConnectionError:
                LOGGER.exception("Periodic Slurm SSH connection failed")
                self._trigger_alert(CONNECTION_FAILURE_REASON)
                self._post_failure_message()
            except Exception:
                LOGGER.exception("Periodic Slurm status query failed")
                self._post_failure_message()

    def _trigger_alert(self, reason: str) -> None:
        if self._alert_workflow is None:
            return
        try:
            self._alert_workflow.trigger(reason)
        except Exception:
            LOGGER.exception("Failed to trigger the Slurm alert workflow")

    def _post_failure_message(self) -> None:
        try:
            self._channel.post_channel(self._channel_id, FAILURE_MESSAGE)
        except Exception:
            LOGGER.exception("Failed to post periodic Slurm status error to Slack")

    def _seconds_until_next_publish(self, now: datetime) -> float:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Clock must return a timezone-aware datetime")
        local_now = now.astimezone(self._schedule_timezone)
        for hour in self._publish_hours:
            candidate = datetime.combine(
                local_now.date(), time(hour=hour), tzinfo=self._schedule_timezone
            )
            if candidate > local_now:
                return (candidate - local_now).total_seconds()
        next_publish = datetime.combine(
            local_now.date() + timedelta(days=1),
            time(hour=self._publish_hours[0]),
            tzinfo=self._schedule_timezone,
        )
        return (next_publish - local_now).total_seconds()
