"""Google Calendar adapter authenticated as one shared bot account."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build  # type: ignore[import-untyped]

from skiml_bot.meetings import BusyPeriod

CALENDAR_SCOPES = (
    "https://www.googleapis.com/auth/calendar.freebusy",
    "https://www.googleapis.com/auth/calendar.events.owned",
)


class GoogleOAuthCalendar:
    def __init__(self, service: Any) -> None:
        self._service = service

    @classmethod
    def from_token_file(cls, token_file: str) -> GoogleOAuthCalendar:
        credentials = Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
            token_file, CALENDAR_SCOPES
        )
        if not credentials.valid:
            if not credentials.expired or not credentials.refresh_token:
                raise ValueError("Google OAuth token is invalid. Run skiml-calendar-auth again.")
            credentials.refresh(Request())
            _write_private_token(Path(token_file), credentials.to_json())
        service = build("calendar", "v3", credentials=credentials, cache_discovery=False)
        return cls(service)

    def free_busy(
        self, emails: tuple[str, ...], start: datetime, end: datetime
    ) -> dict[str, tuple[BusyPeriod, ...]]:
        response = (
            self._service.freebusy()
            .query(
                body={
                    "timeMin": start.isoformat(),
                    "timeMax": end.isoformat(),
                    "items": [{"id": email} for email in emails],
                }
            )
            .execute()
        )
        result: dict[str, tuple[BusyPeriod, ...]] = {}
        calendars = response.get("calendars", {})
        for email in emails:
            calendar = calendars.get(email, {})
            if calendar.get("errors"):
                result[email] = (BusyPeriod(start, end),)
                continue
            result[email] = tuple(
                BusyPeriod(_parse_datetime(period["start"]), _parse_datetime(period["end"]))
                for period in calendar.get("busy", [])
            )
        return result

    def create_invitation(
        self,
        organizer: str,
        attendees: tuple[str, ...],
        title: str,
        start: datetime,
        end: datetime,
    ) -> str:
        body = {
            "summary": title,
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
            "attendees": [{"email": email} for email in attendees],
            "description": "SKIML Slack bot에서 생성한 연구팀 미팅입니다.",
        }
        event: dict[str, Any] = (
            self._service.events()
            .insert(calendarId="primary", body=body, sendUpdates="all")
            .execute()
        )
        return str(event.get("htmlLink", ""))


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def authorize_main() -> None:
    """Authorize the shared Google account and persist an offline token."""
    from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]

    parser = argparse.ArgumentParser(description="Authorize SKIML Bot Google Calendar access")
    parser.add_argument("--client-file", required=True, help="OAuth desktop client JSON file")
    parser.add_argument("--token-file", required=True, help="Output path for the OAuth token")
    args = parser.parse_args()

    flow = InstalledAppFlow.from_client_secrets_file(args.client_file, CALENDAR_SCOPES)
    credentials = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
        authorization_prompt_message="브라우저에서 공용 Google 봇 계정으로 로그인해 주세요: {url}",
    )
    token_path = Path(args.token_file).expanduser().resolve()
    _write_private_token(token_path, credentials.to_json())
    print(f"Google Calendar OAuth token saved to {token_path}")


def _write_private_token(token_path: Path, token_json: str) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token_json, encoding="utf-8")
    token_path.chmod(0o600)
