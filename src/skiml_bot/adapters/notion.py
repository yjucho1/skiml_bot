"""Crawl permitted Notion roots and retrieve relevant lab pages."""

from __future__ import annotations

import re
import threading
import time
from typing import Any

from notion_client import Client

from skiml_bot.knowledge import KnowledgeDocument

TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣_]{2,}")


class NotionWorkspaceSource:
    def __init__(
        self,
        token: str,
        root_page_ids: tuple[str, ...],
        *,
        cache_seconds: int = 600,
        maximum_results: int = 5,
    ) -> None:
        if not root_page_ids:
            raise ValueError("NOTION_ROOT_PAGE_IDS must contain at least one page")
        self._client = Client(auth=token)
        self._root_page_ids = root_page_ids
        self._cache_seconds = cache_seconds
        self._maximum_results = maximum_results
        self._cached_at = 0.0
        self._documents: tuple[KnowledgeDocument, ...] = ()
        self._lock = threading.Lock()

    def search(self, question: str) -> tuple[KnowledgeDocument, ...]:
        documents = self._workspace_documents()
        terms = {term.lower() for term in TOKEN_PATTERN.findall(question)}
        if not terms:
            return ()

        ranked: list[tuple[int, KnowledgeDocument]] = []
        for document in documents:
            title = document.title.lower()
            content = document.content.lower()
            score = sum((title.count(term) * 4) + content.count(term) for term in terms)
            if score:
                ranked.append((score, document))
        ranked.sort(key=lambda item: (-item[0], item[1].title))
        return tuple(document for _, document in ranked[: self._maximum_results])

    def _workspace_documents(self) -> tuple[KnowledgeDocument, ...]:
        with self._lock:
            if self._documents and time.monotonic() - self._cached_at < self._cache_seconds:
                return self._documents
            self._documents = self._crawl()
            self._cached_at = time.monotonic()
            return self._documents

    def _crawl(self) -> tuple[KnowledgeDocument, ...]:
        queue = list(self._root_page_ids)
        visited: set[str] = set()
        documents: list[KnowledgeDocument] = []
        while queue:
            page_id = queue.pop(0)
            if page_id in visited:
                continue
            visited.add(page_id)
            page: Any = self._client.pages.retrieve(page_id=page_id)
            text, child_pages = self._read_blocks(page_id)
            queue.extend(child_pages)
            documents.append(
                KnowledgeDocument(
                    title=_page_title(page),
                    url=str(page.get("url") or f"https://www.notion.so/{page_id.replace('-', '')}"),
                    content=text[:40_000],
                )
            )
        return tuple(documents)

    def _read_blocks(self, block_id: str) -> tuple[str, list[str]]:
        cursor: str | None = None
        text_parts: list[str] = []
        child_pages: list[str] = []
        while True:
            response: Any = self._client.blocks.children.list(
                block_id=block_id,
                start_cursor=cursor,
                page_size=100,
            )
            for raw_block in response.get("results", []):
                block = dict(raw_block)
                block_type = str(block.get("type", ""))
                if block_type == "child_page":
                    child_pages.append(str(block["id"]))
                    continue
                text_parts.extend(_block_text(block))
                if block.get("has_children"):
                    nested_text, nested_pages = self._read_blocks(str(block["id"]))
                    text_parts.append(nested_text)
                    child_pages.extend(nested_pages)
            if not response.get("has_more"):
                break
            cursor = response.get("next_cursor")
        return "\n".join(part for part in text_parts if part), child_pages


def _page_title(page: Any) -> str:
    for value in page.get("properties", {}).values():
        if value.get("type") == "title":
            title = "".join(item.get("plain_text", "") for item in value.get("title", []))
            if title:
                return title
    return "제목 없는 Notion 페이지"


def _block_text(block: dict[str, Any]) -> list[str]:
    payload = block.get(str(block.get("type", "")), {})
    if not isinstance(payload, dict):
        return []
    rich_text = payload.get("rich_text", [])
    return [str(item.get("plain_text", "")) for item in rich_text if item.get("plain_text")]
