"""Periodic publication of the current Slurm server status."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Protocol

from skiml_bot.server_status import ServerStatus

LOGGER = logging.getLogger(__name__)
FAILURE_MESSAGE = "🔴 *[연구실 서버 상태]*\nSSH 또는 `sinfo` 조회에 실패했습니다."


class StatusSource(Protocol):
    def fetch(self) -> ServerStatus: ...


class ChannelPublisher(Protocol):
    def post_channel(self, channel_id: str, text: str) -> None: ...


class StopSignal(Protocol):
    def wait(self, timeout: float) -> bool: ...


class PeriodicServerStatusPublisher:
    def __init__(
        self,
        source: StatusSource,
        channel: ChannelPublisher,
        *,
        channel_id: str,
        interval_seconds: int,
        start_at: datetime,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if not channel_id:
            raise ValueError("Periodic server status channel ID must not be empty")
        if interval_seconds <= 0:
            raise ValueError("Periodic server status interval must be positive")
        if start_at.tzinfo is None or start_at.utcoffset() is None:
            raise ValueError("Periodic server status start time must include a timezone")
        self._source = source
        self._channel = channel
        self._channel_id = channel_id
        self._interval_seconds = interval_seconds
        self._start_at = start_at
        self._clock = clock

    def publish(self) -> None:
        status = self._source.fetch()
        self._channel.post_channel(self._channel_id, status.for_slack())

    def run(self, stop: StopSignal) -> None:
        while True:
            delay = self._seconds_until_next_publish(self._clock())
            if stop.wait(delay):
                return
            try:
                self.publish()
            except Exception:
                LOGGER.exception("Periodic Slurm status query failed")
                try:
                    self._channel.post_channel(self._channel_id, FAILURE_MESSAGE)
                except Exception:
                    LOGGER.exception("Failed to post periodic Slurm status error to Slack")

    def _seconds_until_next_publish(self, now: datetime) -> float:
        if now < self._start_at:
            return (self._start_at - now).total_seconds()
        elapsed = (now - self._start_at).total_seconds()
        completed_intervals = int(elapsed // self._interval_seconds)
        next_publish = self._start_at + timedelta(
            seconds=(completed_intervals + 1) * self._interval_seconds
        )
        return max(0.0, (next_publish - now).total_seconds())
