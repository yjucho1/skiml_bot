"""Channel and thread discussion summaries."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from skiml_bot.research import ThreadReplies


@dataclass(frozen=True)
class DiscussionMessage:
    author_id: str
    text: str


class DiscussionScope(str, Enum):
    CHANNEL = "channel"
    THREAD = "thread"


class DiscussionHistory(Protocol):
    def read_channel(self, channel_id: str) -> tuple[DiscussionMessage, ...]: ...

    def read_thread(self, channel_id: str, thread_ts: str) -> tuple[DiscussionMessage, ...]: ...


class DiscussionSummarizer(Protocol):
    def summarize_discussion(
        self,
        messages: tuple[DiscussionMessage, ...],
        scope: DiscussionScope,
    ) -> str: ...


class DiscussionAssistant:
    """Select the right Slack history scope and summarize it."""

    def __init__(
        self,
        history: DiscussionHistory,
        summarizer: DiscussionSummarizer,
        replies: ThreadReplies,
    ) -> None:
        self._history = history
        self._summarizer = summarizer
        self._replies = replies

    def summarize(
        self,
        channel_id: str,
        request_ts: str,
        source_thread_ts: str | None = None,
    ) -> str:
        if source_thread_ts is None:
            messages = self._history.read_channel(channel_id)
            scope = DiscussionScope.CHANNEL
        else:
            messages = self._history.read_thread(channel_id, source_thread_ts)
            scope = DiscussionScope.THREAD
        summary = self._summarizer.summarize_discussion(messages, scope)
        destination_thread_ts = source_thread_ts or request_ts
        self._replies.post(channel_id, destination_thread_ts, summary)
        return summary
