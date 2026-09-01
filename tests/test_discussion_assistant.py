from dataclasses import dataclass, field

from skiml_bot.discussions import (
    DiscussionAssistant,
    DiscussionMessage,
    DiscussionScope,
)


@dataclass
class FakeHistory:
    channel_reads: list[str] = field(default_factory=list)
    thread_reads: list[tuple[str, str]] = field(default_factory=list)

    def read_channel(self, channel_id: str) -> tuple[DiscussionMessage, ...]:
        self.channel_reads.append(channel_id)
        return (
            DiscussionMessage("U1", "데이터셋은 다음 주까지 정리할게요."),
            DiscussionMessage("U2", "평가 지표는 F1과 AUROC를 같이 봅시다."),
        )

    def read_thread(self, channel_id: str, thread_ts: str) -> tuple[DiscussionMessage, ...]:
        self.thread_reads.append((channel_id, thread_ts))
        return (
            DiscussionMessage("U1", "데이터셋은 다음 주까지 정리할게요."),
            DiscussionMessage("U2", "평가 지표는 F1과 AUROC를 같이 봅시다."),
        )


@dataclass
class FakeDiscussionSummarizer:
    scopes: list[DiscussionScope] = field(default_factory=list)

    def summarize_discussion(
        self,
        messages: tuple[DiscussionMessage, ...],
        scope: DiscussionScope,
    ) -> str:
        assert len(messages) == 2
        self.scopes.append(scope)
        return "*결정*: F1과 AUROC 사용\n*액션*: 데이터셋을 다음 주까지 정리"


@dataclass
class FakeReplies:
    posted: list[tuple[str, str, str]] = field(default_factory=list)

    def post(self, channel_id: str, thread_ts: str, text: str) -> None:
        self.posted.append((channel_id, thread_ts, text))


def test_thread_summary_reads_and_replies_only_in_that_thread() -> None:
    history = FakeHistory()
    replies = FakeReplies()
    summarizer = FakeDiscussionSummarizer()
    assistant = DiscussionAssistant(history, summarizer, replies)

    assistant.summarize(
        channel_id="C-team",
        request_ts="1700000001.000100",
        source_thread_ts="1700000000.000100",
    )

    assert history.thread_reads == [("C-team", "1700000000.000100")]
    assert history.channel_reads == []
    assert summarizer.scopes == [DiscussionScope.THREAD]
    assert replies.posted == [
        (
            "C-team",
            "1700000000.000100",
            "*결정*: F1과 AUROC 사용\n*액션*: 데이터셋을 다음 주까지 정리",
        )
    ]


def test_channel_summary_reads_channel_and_uses_channel_guideline() -> None:
    history = FakeHistory()
    summarizer = FakeDiscussionSummarizer()
    replies = FakeReplies()
    assistant = DiscussionAssistant(history, summarizer, replies)

    assistant.summarize(channel_id="C-team", request_ts="1700000001.000100")

    assert history.channel_reads == ["C-team"]
    assert history.thread_reads == []
    assert summarizer.scopes == [DiscussionScope.CHANNEL]
    assert replies.posted[0][1] == "1700000001.000100"
