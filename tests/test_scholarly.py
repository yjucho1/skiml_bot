from typing import Any

from skiml_bot.adapters.scholarly import (
    ArxivDiscovery,
    CompositeDiscovery,
    OpenAlexDiscovery,
    PaperCandidate,
)


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {
            "results": [
                {
                    "display_name": "Agent Paper",
                    "doi": "https://doi.org/10.1/test",
                    "best_oa_location": {
                        "pdf_url": "https://authors.example/agent-paper.pdf",
                        "landing_page_url": "https://authors.example/paper",
                        "version": "acceptedVersion",
                    },
                },
                {
                    "display_name": "Closed Paper",
                    "best_oa_location": None,
                },
                {
                    "display_name": "Unrelated Open Paper",
                    "best_oa_location": {
                        "pdf_url": "https://unrelated.example/paper.pdf",
                        "version": "publishedVersion",
                    },
                },
            ]
        }


class FakeHttpClient:
    def __init__(self) -> None:
        self.params: dict[str, object] = {}

    def get(self, url: str, *, params: dict[str, object]) -> FakeResponse:
        assert url == "https://api.openalex.org/works"
        self.params = params
        return FakeResponse()


def test_openalex_returns_only_open_access_paper_locations() -> None:
    client = FakeHttpClient()
    discovery = OpenAlexDiscovery(client=client)

    candidates = discovery.find_open_access("Agent Paper 10.1/test")

    assert candidates[0].title == "Agent Paper"
    assert candidates[0].url == "https://authors.example/agent-paper.pdf"
    assert candidates[0].doi == "10.1/test"
    assert candidates[0].version == "acceptedVersion"
    assert len(candidates) == 1
    assert client.params == {"search": "Agent Paper 10.1/test", "per-page": 5}


class FakeArxivResponse:
    text = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/1706.03762v7</id>
        <title>Attention Is All You Need</title>
        <link href="https://arxiv.org/pdf/1706.03762v7" rel="related"
              type="application/pdf" title="pdf"/>
      </entry>
      <entry>
        <id>http://arxiv.org/abs/2104.04692v3</id>
        <title>Not All Attention Is All You Need</title>
        <link href="https://arxiv.org/pdf/2104.04692v3" rel="related"
              type="application/pdf" title="pdf"/>
      </entry>
    </feed>"""

    def raise_for_status(self) -> None:
        return None


class FakeArxivClient:
    def get(self, url: str, *, params: dict[str, object]) -> FakeArxivResponse:
        assert url == "https://export.arxiv.org/api/query"
        assert params["search_query"] == 'ti:"Attention Is All You Need"'
        return FakeArxivResponse()


def test_arxiv_title_search_returns_only_exact_title_matches() -> None:
    candidates = ArxivDiscovery(client=FakeArxivClient()).find_open_access(
        "Attention Is All You Need"
    )

    assert [(candidate.title, candidate.url) for candidate in candidates] == [
        ("Attention Is All You Need", "https://arxiv.org/pdf/1706.03762v7")
    ]


class StubDiscovery:
    def __init__(self, candidates: tuple[PaperCandidate, ...]) -> None:
        self.candidates = candidates
        self.calls = 0

    def find_open_access(self, query: str) -> tuple[PaperCandidate, ...]:
        self.calls += 1
        return self.candidates


def test_composite_stops_after_an_exact_public_source_is_found() -> None:
    exact = PaperCandidate("Agent Paper", "https://arxiv.org/pdf/1234.56789")
    arxiv = StubDiscovery((exact,))
    fallback = StubDiscovery((PaperCandidate("Wrong Paper", "https://wrong.example"),))

    candidates = CompositeDiscovery((arxiv, fallback)).find_open_access("Agent Paper")

    assert candidates == (exact,)
    assert arxiv.calls == 1
    assert fallback.calls == 0
