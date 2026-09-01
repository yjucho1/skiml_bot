"""Scholarly metadata and open-access source discovery."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx


@dataclass(frozen=True)
class PaperCandidate:
    title: str
    url: str
    doi: str | None = None
    version: str | None = None


class PaperDiscovery(Protocol):
    def find_open_access(self, query: str) -> tuple[PaperCandidate, ...]: ...


class CompositeDiscovery:
    """Try precise discovery adapters before broader fallbacks."""

    def __init__(self, discoveries: tuple[PaperDiscovery, ...]) -> None:
        self._discoveries = discoveries

    def find_open_access(self, query: str) -> tuple[PaperCandidate, ...]:
        for discovery in self._discoveries:
            candidates = discovery.find_open_access(query)
            if candidates:
                return candidates
        return ()


_DOI_PATTERN = re.compile(r"\b10\.\S+", re.IGNORECASE)
_ATOM_NAMESPACE = {"atom": "http://www.w3.org/2005/Atom"}


def _normalized_title(value: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())


class ArxivDiscovery:
    """Find exact-title public papers through the arXiv API."""

    def __init__(self, *, client: Any | None = None, timeout_seconds: float = 15) -> None:
        self._client: Any = client or httpx.Client(
            timeout=timeout_seconds,
            headers={"User-Agent": "skiml-bot/0.1 (paper title lookup)"},
        )

    def find_open_access(self, query: str) -> tuple[PaperCandidate, ...]:
        title_query = _DOI_PATTERN.sub("", query).strip().strip('"')
        if not title_query:
            return ()
        response = self._client.get(
            "https://export.arxiv.org/api/query",
            params={
                "search_query": f'ti:"{title_query}"',
                "start": 0,
                "max_results": 5,
            },
        )
        response.raise_for_status()
        try:
            root = ElementTree.fromstring(response.text)
        except ElementTree.ParseError:
            return ()

        expected = _normalized_title(title_query)
        candidates: list[PaperCandidate] = []
        for entry in root.findall("atom:entry", _ATOM_NAMESPACE):
            title_element = entry.find("atom:title", _ATOM_NAMESPACE)
            if title_element is None or not title_element.text:
                continue
            title = " ".join(title_element.text.split())
            if _normalized_title(title) != expected:
                continue
            pdf_url = ""
            for link in entry.findall("atom:link", _ATOM_NAMESPACE):
                if link.attrib.get("type") == "application/pdf":
                    pdf_url = link.attrib.get("href", "")
                    break
            if urlparse(pdf_url).scheme not in {"http", "https"}:
                continue
            candidates.append(PaperCandidate(title, pdf_url, version="submittedVersion"))
        return tuple(candidates)


class OpenAlexDiscovery:
    """Find legal open-access locations indexed by OpenAlex."""

    def __init__(self, *, client: Any | None = None, timeout_seconds: float = 15) -> None:
        self._client: Any = client or httpx.Client(
            timeout=timeout_seconds,
            headers={"User-Agent": "skiml-bot/0.1 (open-access paper discovery)"},
        )

    def find_open_access(self, query: str) -> tuple[PaperCandidate, ...]:
        expected_title = _normalized_title(_DOI_PATTERN.sub("", query))
        response = self._client.get(
            "https://api.openalex.org/works",
            params={"search": query, "per-page": 5},
        )
        response.raise_for_status()
        payload: Any = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            return ()

        candidates: list[PaperCandidate] = []
        seen_urls: set[str] = set()
        for raw_work in payload["results"]:
            if not isinstance(raw_work, dict):
                continue
            raw_location = raw_work.get("best_oa_location")
            if not isinstance(raw_location, dict):
                continue
            raw_url = raw_location.get("pdf_url") or raw_location.get("landing_page_url")
            raw_title = raw_work.get("display_name")
            if not isinstance(raw_url, str) or not isinstance(raw_title, str):
                continue
            if expected_title and _normalized_title(raw_title) != expected_title:
                continue
            if urlparse(raw_url).scheme not in {"http", "https"} or raw_url in seen_urls:
                continue
            raw_doi = raw_work.get("doi")
            raw_version = raw_location.get("version")
            doi = raw_doi.removeprefix("https://doi.org/") if isinstance(raw_doi, str) else None
            version = raw_version if isinstance(raw_version, str) else None
            candidates.append(PaperCandidate(raw_title, raw_url, doi, version))
            seen_urls.add(raw_url)
        return tuple(candidates)
