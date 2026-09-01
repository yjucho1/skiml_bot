from types import SimpleNamespace
from typing import Any

from skiml_bot.adapters.openai_text import OpenAITextAssistant
from skiml_bot.discussions import DiscussionMessage, DiscussionScope


class FakeResponses:
    def __init__(self) -> None:
        self.request: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.request = kwargs
        return SimpleNamespace(output_text="요약 결과")


class FakeOpenAI:
    def __init__(self) -> None:
        self.responses = FakeResponses()


def test_channel_summary_prompt_groups_topics_and_tracks_decisions() -> None:
    client = FakeOpenAI()
    assistant = OpenAITextAssistant("unused", "test-model", client=client)

    assistant.summarize_discussion(
        (
            DiscussionMessage("U1", "데이터셋 정리는 금요일까지 할게요."),
            DiscussionMessage("U2", "다음 주 세미나는 논문 B로 합시다."),
        ),
        DiscussionScope.CHANNEL,
    )

    request = client.responses.request
    assert "서로 다른 주제" in request["instructions"]
    assert "합의되지 않은 제안" in request["instructions"]
    for section in (
        "*[채널 요약]*",
        "요약 범위",
        "전체 흐름",
        "주제별 요약",
        "결정 사항",
        "액션 아이템",
        "미해결 이슈",
    ):
        assert section in request["input"]


def test_thread_summary_prompt_follows_one_topic_to_a_conclusion() -> None:
    client = FakeOpenAI()
    assistant = OpenAITextAssistant("unused", "test-model", client=client)

    assistant.summarize_discussion(
        (
            DiscussionMessage("U1", "평가 지표는 무엇으로 할까요?"),
            DiscussionMessage("U2", "F1과 AUROC를 같이 봅시다."),
        ),
        DiscussionScope.THREAD,
    )

    request = client.responses.request
    assert "하나의 주제" in request["instructions"]
    assert "원문 메시지 작성자" in request["instructions"]
    for section in (
        "*[쓰레드 요약]*",
        "핵심 질문",
        "논의 흐름",
        "합의와 결론",
        "액션 아이템",
        "남은 쟁점",
    ):
        assert section in request["input"]
