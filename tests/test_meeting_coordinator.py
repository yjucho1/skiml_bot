from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from skiml_bot.meetings import BusyPeriod, MeetingCoordinator, MeetingRequest, is_meeting_request


@pytest.mark.parametrize(
    "text",
    (
        "<@U123> 미팅 어레인지",
        "<@U123> 미팅 어레인지 해줘",
        "<@U123> meeting 잡아줘",
        "<@U123> 회의 잡아줘",
        "<@U123> 미팅 예약해주세요",
        "<@U123> Schedule a meeting",
        "<@U123> arrange a call",
    ),
)
def test_meeting_request_aliases_require_a_mention(text: str) -> None:
    assert is_meeting_request(text)


@pytest.mark.parametrize(
    "text",
    (
        "미팅 어레인지",
        "meeting 잡아줘",
        "회의 잡아줘",
        "<@U123> 회의록 요약",
    ),
)
def test_non_mentioned_or_unrelated_meeting_text_is_ignored(text: str) -> None:
    assert not is_meeting_request(text)


def utc(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 25, hour, minute, tzinfo=timezone.utc)


@dataclass
class FakeCalendar:
    busy: dict[str, tuple[BusyPeriod, ...]]
    invitations: list[tuple[str, tuple[str, ...], datetime, datetime]] = field(default_factory=list)

    def free_busy(
        self, emails: tuple[str, ...], start: datetime, end: datetime
    ) -> dict[str, tuple[BusyPeriod, ...]]:
        return {email: self.busy.get(email, ()) for email in emails}

    def create_invitation(
        self,
        organizer: str,
        attendees: tuple[str, ...],
        title: str,
        start: datetime,
        end: datetime,
    ) -> str:
        self.invitations.append((organizer, attendees, start, end))
        return "https://calendar.google.com/event?eid=created"


def test_meeting_is_invited_only_after_confirming_a_common_free_slot() -> None:
    calendar = FakeCalendar(
        busy={
            "alice@example.com": (BusyPeriod(utc(9), utc(10)),),
            "bob@example.com": (BusyPeriod(utc(10), utc(10, 30)),),
        }
    )
    coordinator = MeetingCoordinator(calendar)

    proposal = coordinator.arrange(
        MeetingRequest(
            organizer="alice@example.com",
            participants=("alice@example.com", "bob@example.com"),
            window_start=utc(9),
            window_end=utc(12),
            duration_minutes=60,
        )
    )

    assert [(slot.start, slot.end) for slot in proposal.slots] == [
        (utc(10, 30), utc(11, 30)),
        (utc(11), utc(12)),
    ]
    assert calendar.invitations == []

    event_url = coordinator.confirm(proposal.id, slot_index=0, title="Research sync")
    repeated_url = coordinator.confirm(proposal.id, slot_index=0, title="Research sync")

    assert event_url == "https://calendar.google.com/event?eid=created"
    assert repeated_url == event_url
    assert calendar.invitations == [
        (
            "alice@example.com",
            ("alice@example.com", "bob@example.com"),
            utc(10, 30),
            utc(11, 30),
        )
    ]


def test_meeting_suggestions_skip_nights_and_weekends() -> None:
    calendar = FakeCalendar(busy={})
    coordinator = MeetingCoordinator(calendar)
    friday = datetime(2026, 8, 28, 17, 30, tzinfo=timezone.utc)
    monday = datetime(2026, 8, 31, 11, 0, tzinfo=timezone.utc)

    proposal = coordinator.arrange(
        MeetingRequest(
            organizer="alice@example.com",
            participants=("bob@example.com",),
            window_start=friday,
            window_end=monday,
            duration_minutes=60,
            working_hour_start=10,
            working_hour_end=18,
        )
    )

    assert [(slot.start, slot.end) for slot in proposal.slots] == [
        (
            datetime(2026, 8, 31, 10, 0, tzinfo=timezone.utc),
            monday,
        )
    ]
