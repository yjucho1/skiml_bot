"""Grounded answers over lab knowledge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class KnowledgeDocument:
    title: str
    url: str
    content: str


@dataclass(frozen=True)
class KnowledgeAnswer:
    text: str
    sources: tuple[tuple[str, str], ...]

    def for_slack(self) -> str:
        if not self.sources:
            return self.text
        links = "\n".join(f"• <{url}|{title}>" for title, url in self.sources)
        return f"{self.text}\n\n*출처*\n{links}"


class KnowledgeSource(Protocol):
    def search(self, question: str) -> tuple[KnowledgeDocument, ...]: ...


class AnswerGenerator(Protocol):
    def answer(self, question: str, documents: tuple[KnowledgeDocument, ...]) -> str: ...


class LabKnowledge:
    """Answer only from retrieved documents and expose their provenance."""

    def __init__(self, source: KnowledgeSource, generator: AnswerGenerator) -> None:
        self._source = source
        self._generator = generator

    def answer(self, question: str) -> KnowledgeAnswer:
        documents = self._source.search(question)
        if not documents:
            return KnowledgeAnswer(
                text="연구실 Notion에서 관련 근거를 찾지 못했습니다.",
                sources=(),
            )
        text = self._generator.answer(question, documents)
        sources = tuple(dict.fromkeys((document.title, document.url) for document in documents))
        return KnowledgeAnswer(text=text, sources=sources)
