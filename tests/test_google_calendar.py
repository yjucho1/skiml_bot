from datetime import datetime, timezone
from typing import Any

from skiml_bot.adapters.google_calendar import GoogleOAuthCalendar


class FakeRequest:
    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response

    def execute(self) -> dict[str, Any]:
        return self._response


class FakeEvents:
    def __init__(self) -> None:
        self.inserted: dict[str, Any] | None = None

    def insert(self, **kwargs: Any) -> FakeRequest:
        self.inserted = kwargs
        return FakeRequest({"htmlLink": "https://calendar.google.com/event?eid=shared"})


class FakeService:
    def __init__(self) -> None:
        self.event_api = FakeEvents()

    def events(self) -> FakeEvents:
        return self.event_api


def test_shared_account_creates_invitation_on_primary_calendar() -> None:
    service = FakeService()
    calendar = GoogleOAuthCalendar(service)
    start = datetime(2026, 9, 2, 10, tzinfo=timezone.utc)
    end = datetime(2026, 9, 2, 11, tzinfo=timezone.utc)

    event_url = calendar.create_invitation(
        organizer="requester@example.com",
        attendees=("requester@example.com", "member@example.com"),
        title="Research sync",
        start=start,
        end=end,
    )

    assert event_url == "https://calendar.google.com/event?eid=shared"
    assert service.event_api.inserted == {
        "calendarId": "primary",
        "body": {
            "summary": "Research sync",
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
            "attendees": [
                {"email": "requester@example.com"},
                {"email": "member@example.com"},
            ],
            "description": "SKIML Slack bot에서 생성한 연구팀 미팅입니다.",
        },
        "sendUpdates": "all",
    }
