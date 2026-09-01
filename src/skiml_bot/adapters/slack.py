"""Slack Web API adapter."""

from __future__ import annotations

from typing import Any

from slack_sdk import WebClient

from skiml_bot.discussions import DiscussionMessage


class SlackGateway:
    def __init__(self, client: WebClient) -> None:
        self._client = client

    def post(self, channel_id: str, thread_ts: str, text: str) -> None:
        self._client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=text)

    def post_channel(self, channel_id: str, text: str) -> None:
        self._client.chat_postMessage(channel=channel_id, text=text)

    def read_channel(self, channel_id: str) -> tuple[DiscussionMessage, ...]:
        response = self._client.conversations_history(channel=channel_id, limit=200)
        return _discussion_messages(response.get("messages", []))

    def read_thread(self, channel_id: str, thread_ts: str) -> tuple[DiscussionMessage, ...]:
        response = self._client.conversations_replies(channel=channel_id, ts=thread_ts, limit=200)
        return _discussion_messages(response.get("messages", []))

    def channel_member_emails(self, channel_id: str) -> tuple[str, ...]:
        emails: list[str] = []
        cursor: str | None = None
        while True:
            response = self._client.conversations_members(
                channel=channel_id, limit=200, cursor=cursor
            )
            members: list[str] = list(response.get("members", []))
            for user_id in members:
                user: dict[str, Any] = dict(self._client.users_info(user=user_id).get("user", {}))
                profile = user.get("profile", {})
                email = profile.get("email")
                if email and not user.get("deleted") and not user.get("is_bot"):
                    emails.append(str(email))
            metadata: dict[str, Any] = dict(response.get("response_metadata", {}))
            cursor = metadata.get("next_cursor") or None
            if cursor is None:
                break
        return tuple(dict.fromkeys(emails))

    def user_email(self, user_id: str) -> str:
        user: dict[str, Any] = dict(self._client.users_info(user=user_id).get("user", {}))
        email = user.get("profile", {}).get("email")
        if not email:
            raise ValueError(f"Slack user {user_id} has no visible email")
        return str(email)


def _discussion_messages(messages: list[Any]) -> tuple[DiscussionMessage, ...]:
    result: list[DiscussionMessage] = []
    for message in reversed(messages):
        if message.get("bot_id") or message.get("subtype"):
            continue
        text = str(message.get("text", "")).strip()
        if text:
            result.append(DiscussionMessage(str(message.get("user", "unknown")), text))
    return tuple(result)
