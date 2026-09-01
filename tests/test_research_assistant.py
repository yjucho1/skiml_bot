from dataclasses import dataclass, field

import pytest

from skiml_bot.research import (
    ResearchAssistant,
    SlackMessage,
    extract_paper_reference,
    is_paper_summary_request,
)


def test_url_before_summary_command_is_recognized() -> None:
    assert is_paper_summary_request(
        "<@USKIML> <https://arxiv.org/abs/2401.12345|논문 링크> 요약해줘"
    )


@pytest.mark.parametrize(
    "command",
    ["요약해줘", "요약", "요약해", "써머리", "summary", "Summary", "SUMMARY"],
)
def test_common_summary_aliases_are_case_insensitive(command: str) -> None:
    assert is_paper_summary_request(
        f"<@USKIML> {command} <https://arxiv.org/abs/2401.12345|논문 링크>"
    )


def test_paper_title_is_extracted_when_summary_alias_is_provided() -> None:
    assert (
        extract_paper_reference('<@USKIML> "Attention Is All You Need" SUMMARY')
        == "Attention Is All You Need"
    )


def test_channel_and_thread_summary_commands_are_not_paper_titles() -> None:
    assert extract_paper_reference("<@USKIML> 채널 요약") is None
    assert extract_paper_reference("<@USKIML> 쓰레드 요약해") is None


def test_url_only_message_is_handled_as_paper_summary() -> None:
    summarizer = FakeSummarizer()
    replies = FakeThreadReplies()
    assistant = ResearchAssistant(summarizer=summarizer, replies=replies)

    handled = assistant.handle(
        SlackMessage(
            event_id="Ev-url-only",
            channel_id="C-team-anywhere",
            ts="1700000000.000120",
            text="<@USKIML> <https://arxiv.org/abs/2401.12345>",
        )
    )

    assert handled is True
    assert summarizer.calls == ["https://arxiv.org/abs/2401.12345"]
    assert replies.posted[0][1] == "1700000000.000120"


def test_url_only_without_bot_mention_is_ignored() -> None:
    summarizer = FakeSummarizer()
    assistant = ResearchAssistant(summarizer=summarizer, replies=FakeThreadReplies())

    handled = assistant.handle(
        SlackMessage(
            event_id="Ev-unmentioned-url",
            channel_id="C-team-anywhere",
            ts="1700000000.000130",
            text="<https://arxiv.org/abs/2401.12345>",
        )
    )

    assert handled is False
    assert summarizer.calls == []


@dataclass
class FakeSummarizer:
    calls: list[str] = field(default_factory=list)

    def summarize_paper(self, reference: str) -> str:
        self.calls.append(reference)
        return "핵심: 표현 학습을 개선하는 새로운 대조 학습 방법을 제안합니다."


@dataclass
class FakeThreadReplies:
    posted: list[tuple[str, str, str]] = field(default_factory=list)

    def post(self, channel_id: str, thread_ts: str, text: str) -> None:
        self.posted.append((channel_id, thread_ts, text))


def test_paper_title_request_is_sent_to_the_research_agent() -> None:
    summarizer = FakeSummarizer()
    assistant = ResearchAssistant(summarizer=summarizer, replies=FakeThreadReplies())

    handled = assistant.handle(
        SlackMessage(
            event_id="Ev-paper-title",
            channel_id="C-team-anywhere",
            ts="1700000000.000140",
            text='<@USKIML> "Attention Is All You Need" summary',
        )
    )

    assert handled is True
    assert summarizer.calls == ["Attention Is All You Need"]


def test_explicit_summary_mention_works_in_any_channel_and_is_idempotent() -> None:
    summarizer = FakeSummarizer()
    replies = FakeThreadReplies()
    assistant = ResearchAssistant(
        summarizer=summarizer,
        replies=replies,
    )
    message = SlackMessage(
        event_id="Ev-1",
        channel_id="C-team-anywhere",
        ts="1700000000.000100",
        text="<@USKIML> 요약해줘 https://arxiv.org/abs/2401.12345",
    )

    assistant.handle(message)
    assistant.handle(message)

    assert summarizer.calls == ["https://arxiv.org/abs/2401.12345"]
    assert replies.posted == [
        (
            "C-team-anywhere",
            "1700000000.000100",
            "핵심: 표현 학습을 개선하는 새로운 대조 학습 방법을 제안합니다.",
        )
    ]


def test_plain_url_without_summary_request_is_ignored() -> None:
    summarizer = FakeSummarizer()
    replies = FakeThreadReplies()
    assistant = ResearchAssistant(summarizer=summarizer, replies=replies)

    handled = assistant.handle(
        SlackMessage(
            event_id="Ev-plain-link",
            channel_id="C-team-anywhere",
            ts="1700000000.000150",
            text="읽어볼 논문 https://arxiv.org/abs/2401.12345",
        )
    )

    assert handled is False
    assert summarizer.calls == []
    assert replies.posted == []


def test_summary_requested_in_a_thread_replies_to_that_thread() -> None:
    replies = FakeThreadReplies()
    assistant = ResearchAssistant(summarizer=FakeSummarizer(), replies=replies)

    assistant.handle(
        SlackMessage(
            event_id="Ev-thread-link",
            channel_id="C-team-anywhere",
            ts="1700000000.000300",
            thread_ts="1700000000.000250",
            text="<@USKIML> 요약해줘 https://arxiv.org/abs/2401.12345",
        )
    )

    assert replies.posted[0][1] == "1700000000.000250"


def test_slack_formatted_link_passes_only_the_real_url_to_the_summarizer() -> None:
    summarizer = FakeSummarizer()
    assistant = ResearchAssistant(
        summarizer=summarizer,
        replies=FakeThreadReplies(),
    )

    assistant.handle(
        SlackMessage(
            event_id="Ev-slack-link",
            channel_id="C04L953EAGP",
            ts="1700000000.000200",
            text=("<@USKIML> 요약해줘 <https://arxiv.org/abs/1706.03762|arxiv.org/abs/1706.03762>"),
        )
    )

    assert summarizer.calls == ["https://arxiv.org/abs/1706.03762"]
