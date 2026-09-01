"""Meeting availability and invitation workflow."""

from __future__ import annotations

import re
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

SLACK_MENTION_PATTERN = re.compile(r"<@[A-Z0-9]+>")
MEETING_NOUN = r"(?:미팅|회의|meeting|meet|call)"
KOREAN_MEETING_ACTION = (
    r"(?:어레인지(?:\s*해\s*(?:줘|주세요))?"
    r"|(?:일정\s*)?잡아\s*(?:줘|주세요|줄래|주실래요)?"
    r"|예약\s*해\s*(?:줘|주세요)?)"
)
MEETING_REQUEST_PATTERN = re.compile(
    rf"(?:{MEETING_NOUN}\s*(?:을|를)?\s*(?:{KOREAN_MEETING_ACTION}|schedule|arrange|book)"
    rf"|(?:schedule|arrange|book|set\s*up)\s+(?:a\s+)?{MEETING_NOUN})",
    re.IGNORECASE,
)


def is_meeting_request(text: str) -> bool:
    """Return whether text is a mentioned request to arrange a meeting."""
    if SLACK_MENTION_PATTERN.search(text) is None:
        return False
    command = SLACK_MENTION_PATTERN.sub("", text).strip()
    return MEETING_REQUEST_PATTERN.search(command) is not None


@dataclass(frozen=True)
class BusyPeriod:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class TimeSlot:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class MeetingRequest:
    organizer: str
    participants: tuple[str, ...]
    window_start: datetime
    window_end: datetime
    duration_minutes: int = 60
    working_hour_start: int = 9
    working_hour_end: int = 18
    working_weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)


@dataclass(frozen=True)
class MeetingProposal:
    id: str
    slots: tuple[TimeSlot, ...]


class Calendar(Protocol):
    def free_busy(
        self, emails: tuple[str, ...], start: datetime, end: datetime
    ) -> dict[str, tuple[BusyPeriod, ...]]: ...

    def create_invitation(
        self,
        organizer: str,
        attendees: tuple[str, ...],
        title: str,
        start: datetime,
        end: datetime,
    ) -> str: ...


@dataclass
class _PendingProposal:
    request: MeetingRequest
    slots: tuple[TimeSlot, ...]
    event_url: str | None = None


class MeetingCoordinator:
    """Find common availability and require confirmation before writing calendars."""

    def __init__(self, calendar: Calendar, *, maximum_suggestions: int = 3) -> None:
        self._calendar = calendar
        self._maximum_suggestions = maximum_suggestions
        self._proposals: dict[str, _PendingProposal] = {}
        self._proposal_lock = threading.Lock()

    def arrange(self, request: MeetingRequest) -> MeetingProposal:
        self._validate(request)
        participants = tuple(dict.fromkeys((request.organizer, *request.participants)))
        busy_by_email = self._calendar.free_busy(
            participants, request.window_start, request.window_end
        )
        duration = timedelta(minutes=request.duration_minutes)
        cursor = request.window_start
        slots: list[TimeSlot] = []

        while cursor + duration <= request.window_end:
            candidate = TimeSlot(cursor, cursor + duration)
            if self._within_working_hours(candidate, request) and self._everyone_is_free(
                candidate, participants, busy_by_email
            ):
                slots.append(candidate)
                if len(slots) == self._maximum_suggestions:
                    break
            cursor += timedelta(minutes=30)

        proposal_id = secrets.token_urlsafe(12)
        pending = _PendingProposal(request=request, slots=tuple(slots))
        with self._proposal_lock:
            self._proposals[proposal_id] = pending
        return MeetingProposal(id=proposal_id, slots=pending.slots)

    def confirm(self, proposal_id: str, slot_index: int, title: str) -> str:
        with self._proposal_lock:
            try:
                proposal = self._proposals[proposal_id]
            except KeyError as error:
                raise ValueError("Unknown or expired meeting proposal") from error
            if proposal.event_url is not None:
                return proposal.event_url
            if slot_index < 0:
                raise ValueError("Invalid meeting slot")
            try:
                slot = proposal.slots[slot_index]
            except IndexError as error:
                raise ValueError("Invalid meeting slot") from error

            participants = tuple(
                dict.fromkeys((proposal.request.organizer, *proposal.request.participants))
            )
            proposal.event_url = self._calendar.create_invitation(
                proposal.request.organizer,
                participants,
                title,
                slot.start,
                slot.end,
            )
            return proposal.event_url

    @staticmethod
    def _within_working_hours(candidate: TimeSlot, request: MeetingRequest) -> bool:
        return (
            candidate.start.weekday() in request.working_weekdays
            and candidate.end.date() == candidate.start.date()
            and candidate.start.hour >= request.working_hour_start
            and (
                candidate.end.hour < request.working_hour_end
                or (
                    candidate.end.hour == request.working_hour_end
                    and candidate.end.minute == 0
                    and candidate.end.second == 0
                )
            )
        )

    @staticmethod
    def _everyone_is_free(
        candidate: TimeSlot,
        participants: tuple[str, ...],
        busy_by_email: dict[str, tuple[BusyPeriod, ...]],
    ) -> bool:
        return all(
            not any(
                period.start < candidate.end and period.end > candidate.start
                for period in busy_by_email.get(email, ())
            )
            for email in participants
        )

    @staticmethod
    def _validate(request: MeetingRequest) -> None:
        if request.duration_minutes <= 0:
            raise ValueError("Meeting duration must be positive")
        if not 0 <= request.working_hour_start < request.working_hour_end <= 24:
            raise ValueError("Working hours must be within a single day")
        if request.window_start.tzinfo is None or request.window_end.tzinfo is None:
            raise ValueError("Meeting window must include a timezone")
        if request.window_start >= request.window_end:
            raise ValueError("Meeting window must have a positive duration")
