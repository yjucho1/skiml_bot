"""Fetch readable text from research URLs."""

from __future__ import annotations

import ipaddress
import json
import re
import socket
from html import unescape
from html.parser import HTMLParser
from io import BytesIO
from typing import cast
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from pypdf import PdfReader


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._hidden_depth == 0 and data.strip():
            self.parts.append(data.strip())


class WebContentExtractor:
    def __init__(
        self,
        *,
        timeout_seconds: float = 20,
        maximum_chars: int = 160_000,
        maximum_bytes: int = 20_000_000,
    ) -> None:
        self._client = httpx.Client(
            follow_redirects=False,
            timeout=timeout_seconds,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 Chrome/139.0.0.0 Safari/537.36 skiml-bot/0.1"
                )
            },
        )
        self._maximum_chars = maximum_chars
        self._maximum_bytes = maximum_bytes

    def extract(self, url: str) -> str:
        content, content_type, encoding, final_url = self._download(resolve_original_paper_url(url))
        if "application/pdf" in content_type or final_url.lower().endswith(".pdf"):
            reader = PdfReader(BytesIO(content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            access_scope = "접근 범위: 원문 전체 PDF"
        else:
            decoded = content.decode(encoding or "utf-8", errors="replace")
            ieee_metadata = extract_ieee_metadata(decoded)
            if ieee_metadata is not None:
                return ieee_metadata[: self._maximum_chars]
            parser = _VisibleTextParser()
            parser.feed(decoded)
            text = "\n".join(parser.parts)
            access_scope = "접근 범위: 공개 웹페이지"
        compact = "\n".join(line for line in text.splitlines() if line.strip())
        if not compact:
            raise ValueError("Research document contains no readable text")
        return f"{access_scope}\n{compact}"[: self._maximum_chars]

    def _download(self, url: str) -> tuple[bytes, str, str | None, str]:
        current_url = url
        for _ in range(6):
            validate_public_url(current_url)
            with self._client.stream(
                "GET", current_url, headers=_request_headers(current_url)
            ) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("Redirect response has no location")
                    current_url = urljoin(current_url, location)
                    continue
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > self._maximum_bytes:
                        raise ValueError("Research document is too large")
                return (
                    bytes(content),
                    response.headers.get("content-type", "").lower(),
                    response.encoding,
                    current_url,
                )
        raise ValueError("Too many redirects while fetching research document")


_ARXIV_HOSTS = {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}
_ARXIV_DOI_PATTERN = re.compile(r"^/10\.48550/arxiv\.(?P<identifier>[^/?#]+(?:/[^/?#]+)?)$", re.I)
_IEEE_HOSTS = {"ieeexplore.ieee.org", "www.ieeexplore.ieee.org"}
_IEEE_METADATA_MARKER = "xplGlobal.document.metadata="


def resolve_original_paper_url(url: str) -> str:
    """Resolve known paper landing pages to their original full-text documents."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/")

    if hostname in _ARXIV_HOSTS:
        match = re.match(r"^/(?:abs|html)/(?P<identifier>.+)$", path, re.I)
        if match:
            return f"https://arxiv.org/pdf/{match.group('identifier')}"

    if hostname in {"doi.org", "dx.doi.org"}:
        match = _ARXIV_DOI_PATTERN.match(path)
        if match:
            return f"https://arxiv.org/pdf/{match.group('identifier')}"

    if hostname in _IEEE_HOSTS:
        match = re.match(r"^/document/(?P<identifier>\d+)$", path, re.I)
        if match:
            identifier = match.group("identifier")
            return f"https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={identifier}"

    return url


def _request_headers(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() not in _IEEE_HOSTS:
        return {}
    article_number = parse_qs(parsed.query).get("arnumber", [""])[0]
    if not article_number.isdigit():
        return {}
    return {"Referer": f"https://ieeexplore.ieee.org/document/{article_number}/"}


def extract_ieee_metadata(html: str) -> str | None:
    """Extract the publisher-provided abstract when IEEE full text is unavailable."""
    marker_index = html.find(_IEEE_METADATA_MARKER)
    if marker_index < 0:
        return None
    json_start = marker_index + len(_IEEE_METADATA_MARKER)
    try:
        raw_metadata, _ = json.JSONDecoder().raw_decode(html[json_start:].lstrip())
    except json.JSONDecodeError:
        return None
    if not isinstance(raw_metadata, dict):
        return None
    metadata = cast(dict[str, object], raw_metadata)

    title = _text_field(metadata, "formulaStrippedArticleTitle") or _text_field(
        metadata, "displayDocTitle"
    )
    abstract = _text_field(metadata, "abstract")
    if not title and not abstract:
        return None

    authors: list[str] = []
    raw_authors = metadata.get("authors")
    if isinstance(raw_authors, list):
        for author in raw_authors:
            if isinstance(author, dict) and isinstance(author.get("name"), str):
                authors.append(unescape(author["name"]))

    keywords: list[str] = []
    raw_keyword_groups = metadata.get("keywords")
    if isinstance(raw_keyword_groups, list):
        for group in raw_keyword_groups:
            if not isinstance(group, dict) or not isinstance(group.get("kwd"), list):
                continue
            keywords.extend(str(keyword) for keyword in group["kwd"] if keyword)

    is_open_access = metadata.get("openAccessFlag") in {True, "T", "true"}
    scope = "접근 범위: 초록 및 서지정보만"
    if is_open_access:
        scope += " (공개 원문 PDF를 가져오지 못함)"
    else:
        scope += " (IEEE 원문 PDF는 구독 또는 구매 필요)"

    fields = [
        scope,
        f"제목: {title}",
        f"저자: {', '.join(authors)}" if authors else "",
        f"학술지: {_text_field(metadata, 'publicationTitle')}",
        f"발행일: {_text_field(metadata, 'publicationDate')}",
        f"DOI: {_text_field(metadata, 'doiLink')}",
        f"키워드: {', '.join(dict.fromkeys(keywords))}" if keywords else "",
        f"초록: {abstract}",
    ]
    return "\n".join(field for field in fields if field and not field.endswith(": "))


def _text_field(metadata: dict[str, object], key: str) -> str:
    value = metadata.get(key)
    return unescape(value).strip() if isinstance(value, str) else ""


def validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    hostname = parsed.hostname
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise ValueError("Research links must use a public HTTP URL")
    if hostname.lower() == "localhost" or hostname.lower().endswith(".localhost"):
        raise ValueError("Research links must use a public HTTP URL")

    try:
        addresses = {ipaddress.ip_address(hostname)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(result[4][0])
                for result in socket.getaddrinfo(hostname, parsed.port or 443)
            }
        except socket.gaierror as error:
            raise ValueError("Research links must use a resolvable public HTTP URL") from error
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("Research links must use a public HTTP URL")
