"""Research sharing workflow."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Protocol

URL_PATTERN = re.compile(r"https?://[^\s<>|]+")
URL_TOKEN_PATTERN = re.compile(r"(?:<https?://[^|>\s]+(?:\|[^>]*)?>|https?://[^\s<>]+)")
MENTION_PATTERN = re.compile(r"<@[A-Z0-9]+>")
SUMMARY_ALIAS = r"(?:요약(?:\s*해(?:\s*(?:줘|주세요))?)?|[써서]머리|summar(?:y|ize))"
SUMMARY_REQUEST_PATTERN = re.compile(SUMMARY_ALIAS, re.IGNORECASE)
TITLE_AFTER_COMMAND_PATTERN = re.compile(
    rf"^\s*{SUMMARY_ALIAS}\s+(?P<title>.+?)\s*$", re.IGNORECASE
)
TITLE_BEFORE_COMMAND_PATTERN = re.compile(
    rf"^\s*(?P<title>.+?)\s+{SUMMARY_ALIAS}\s*$", re.IGNORECASE
)


def has_summary_request(text: str) -> bool:
    return SUMMARY_REQUEST_PATTERN.search(text) is not None


def _is_url_only_after_mention(text: str) -> bool:
    without_mentions = MENTION_PATTERN.sub("", text).strip()
    return URL_TOKEN_PATTERN.fullmatch(without_mentions) is not None


def extract_paper_reference(text: str) -> str | None:
    """Extract a URL or title from a mentioned paper-summary request."""
    if MENTION_PATTERN.search(text) is None:
        return None
    url_match = URL_PATTERN.search(text)
    if url_match is not None:
        if has_summary_request(text) or _is_url_only_after_mention(text):
            return url_match.group(0).rstrip(".,)")
        return None

    command = MENTION_PATTERN.sub("", text).strip()
    for pattern in (TITLE_AFTER_COMMAND_PATTERN, TITLE_BEFORE_COMMAND_PATTERN):
        match = pattern.fullmatch(command)
        if match is None:
            continue
        title = match.group("title").strip().strip("\"'“”‘’")
        if title and title.casefold() not in {"채널", "쓰레드", "스레드"}:
            return title
    return None


def is_paper_summary_request(text: str) -> bool:
    return extract_paper_reference(text) is not None


@dataclass(frozen=True)
class SlackMessage:
    event_id: str
    channel_id: str
    ts: str
    text: str
    thread_ts: str | None = None


class PaperResearcher(Protocol):
    def summarize_paper(self, reference: str) -> str: ...


class ThreadReplies(Protocol):
    def post(self, channel_id: str, thread_ts: str, text: str) -> None: ...


class ResearchAssistant:
    """Turn research links into idempotent thread summaries."""

    def __init__(
        self,
        summarizer: PaperResearcher,
        replies: ThreadReplies,
    ) -> None:
        self._summarizer = summarizer
        self._replies = replies
        self._processed_events: set[str] = set()
        self._event_lock = threading.Lock()

    def handle(self, message: SlackMessage) -> bool:
        reference = extract_paper_reference(message.text)
        if reference is None:
            return False

        with self._event_lock:
            if message.event_id in self._processed_events:
                return False
            self._processed_events.add(message.event_id)
        try:
            summary = self._summarizer.summarize_paper(reference)
            self._replies.post(message.channel_id, message.thread_ts or message.ts, summary)
        except Exception:
            with self._event_lock:
                self._processed_events.discard(message.event_id)
            raise
        return True
