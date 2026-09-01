from types import SimpleNamespace
from typing import Any

from skiml_bot.adapters.paper_agent import OpenAIPaperResearchAgent
from skiml_bot.adapters.scholarly import PaperCandidate


class FakeReader:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def extract(self, url: str) -> str:
        self.urls.append(url)
        if "authors.example" in url:
            return "접근 범위: 원문 전체 PDF\nFULL PAPER: accuracy 91.2"
        return "접근 범위: 초록 및 서지정보만\n제목: Agent Paper\nDOI: 10.1/test"


class FakeDiscovery:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def find_open_access(self, query: str) -> tuple[PaperCandidate, ...]:
        self.queries.append(query)
        return (
            PaperCandidate(
                title="Agent Paper",
                url="https://authors.example/agent-paper.pdf",
                doi="10.1/test",
                version="acceptedVersion",
            ),
        )


class FakeResponses:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self._responses = iter(
            (
                SimpleNamespace(
                    output=[
                        SimpleNamespace(
                            type="function_call",
                            name="find_open_access_sources",
                            arguments='{"query":"Agent Paper 10.1/test"}',
                            call_id="call-search",
                        )
                    ],
                    output_text="",
                ),
                SimpleNamespace(
                    output=[
                        SimpleNamespace(
                            type="function_call",
                            name="read_paper_source",
                            arguments=('{"url":"https://authors.example/agent-paper.pdf"}'),
                            call_id="call-read",
                        )
                    ],
                    output_text="",
                ),
                SimpleNamespace(
                    output=[SimpleNamespace(type="message")],
                    output_text="*[논문 요약 · 조사 에이전트]*\n원문 전체 기반 요약",
                ),
            )
        )

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.requests.append(kwargs)
        return next(self._responses)


class FakeOpenAI:
    def __init__(self) -> None:
        self.responses = FakeResponses()


def test_agent_finds_and_reads_open_copy_before_final_summary() -> None:
    reader = FakeReader()
    discovery = FakeDiscovery()
    client = FakeOpenAI()
    agent = OpenAIPaperResearchAgent(
        "unused",
        "test-model",
        reader=reader,
        discovery=discovery,
        client=client,
    )

    result = agent.summarize_paper("https://publisher.example/paper")

    assert result.startswith("*[논문 요약 · 조사 에이전트]*")
    assert reader.urls == [
        "https://publisher.example/paper",
        "https://authors.example/agent-paper.pdf",
    ]
    assert discovery.queries == ["Agent Paper 10.1/test"]
    final_input = client.responses.requests[-1]["input"]
    assert any(
        item.get("type") == "function_call_output" and "FULL PAPER" in item.get("output", "")
        for item in final_input
        if isinstance(item, dict)
    )


def test_agent_resolves_a_paper_title_before_reading_the_source() -> None:
    reader = FakeReader()
    discovery = FakeDiscovery()
    agent = OpenAIPaperResearchAgent(
        "unused",
        "test-model",
        reader=reader,
        discovery=discovery,
        client=FakeOpenAI(),
    )

    result = agent.summarize_paper("Agent Paper")

    assert result.startswith("*[논문 요약 · 조사 에이전트]*")
    assert discovery.queries == ["Agent Paper 10.1/test"]
    assert reader.urls == ["https://authors.example/agent-paper.pdf"]


def test_agent_cannot_read_a_url_that_discovery_did_not_return() -> None:
    client = FakeOpenAI()
    client.responses._responses = iter(
        (
            SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="read_paper_source",
                        arguments='{"url":"https://attacker.example/instructions"}',
                        call_id="call-unsafe",
                    )
                ],
                output_text="",
            ),
        )
    )
    reader = FakeReader()
    agent = OpenAIPaperResearchAgent(
        "unused",
        "test-model",
        reader=reader,
        discovery=FakeDiscovery(),
        client=client,
    )

    try:
        agent.summarize_paper("https://publisher.example/paper")
    except ValueError as error:
        assert "unapproved URL" in str(error)
    else:
        raise AssertionError("agent must reject undiscovered URLs")

    assert reader.urls == ["https://publisher.example/paper"]


def test_agent_cannot_finish_abstract_only_research_before_open_copy_search() -> None:
    client = FakeOpenAI()
    client.responses._responses = iter(
        (
            SimpleNamespace(
                output=[SimpleNamespace(type="message")],
                output_text="premature abstract summary",
            ),
            SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="find_open_access_sources",
                        arguments='{"query":"Agent Paper 10.1/test"}',
                        call_id="call-required-search",
                    )
                ],
                output_text="",
            ),
            SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="read_paper_source",
                        arguments='{"url":"https://authors.example/agent-paper.pdf"}',
                        call_id="call-required-read",
                    )
                ],
                output_text="",
            ),
            SimpleNamespace(
                output=[SimpleNamespace(type="message")],
                output_text="*[논문 요약 · 조사 에이전트]*\n검증 완료",
            ),
        )
    )
    agent = OpenAIPaperResearchAgent(
        "unused",
        "test-model",
        reader=FakeReader(),
        discovery=FakeDiscovery(),
        client=client,
    )

    result = agent.summarize_paper("https://publisher.example/paper")

    assert result.endswith("검증 완료")
    assert len(client.responses.requests) == 4
    retry_input = client.responses.requests[1]["input"]
    assert any(
        isinstance(item, dict) and "공개본 검색을 먼저 수행" in item.get("content", "")
        for item in retry_input
    )


class FallbackReader(FakeReader):
    def extract(self, url: str) -> str:
        self.urls.append(url)
        if "blocked" in url:
            raise ValueError("403 Forbidden")
        if "working" in url:
            return "접근 범위: 원문 전체 PDF\nVERIFIED PAPER"
        return "접근 범위: 초록 및 서지정보만\n제목: Agent Paper"


class FallbackDiscovery:
    def find_open_access(self, query: str) -> tuple[PaperCandidate, ...]:
        return (
            PaperCandidate("Agent Paper", "https://blocked.example/paper.pdf"),
            PaperCandidate("Agent Paper", "https://working.example/paper.pdf"),
        )


def test_agent_can_try_another_approved_source_after_a_read_failure() -> None:
    client = FakeOpenAI()
    client.responses._responses = iter(
        (
            SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="find_open_access_sources",
                        arguments='{"query":"Agent Paper"}',
                        call_id="call-search",
                    )
                ],
                output_text="",
            ),
            SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="read_paper_source",
                        arguments='{"url":"https://blocked.example/paper.pdf"}',
                        call_id="call-blocked",
                    )
                ],
                output_text="",
            ),
            SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="read_paper_source",
                        arguments='{"url":"https://working.example/paper.pdf"}',
                        call_id="call-working",
                    )
                ],
                output_text="",
            ),
            SimpleNamespace(
                output=[SimpleNamespace(type="message")],
                output_text="*[논문 요약 · 조사 에이전트]*\n복구 성공",
            ),
        )
    )
    reader = FallbackReader()
    agent = OpenAIPaperResearchAgent(
        "unused",
        "test-model",
        reader=reader,
        discovery=FallbackDiscovery(),
        client=client,
    )

    result = agent.summarize_paper("Agent Paper")

    assert result.endswith("복구 성공")
    assert reader.urls == [
        "https://blocked.example/paper.pdf",
        "https://working.example/paper.pdf",
    ]
