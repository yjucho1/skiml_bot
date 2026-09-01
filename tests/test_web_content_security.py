import pytest

from skiml_bot.adapters.content import (
    extract_ieee_metadata,
    resolve_original_paper_url,
    validate_public_url,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://arxiv.org/abs/2606.10684", "https://arxiv.org/pdf/2606.10684"),
        ("https://arxiv.org/html/2606.10684v2", "https://arxiv.org/pdf/2606.10684v2"),
        (
            "https://doi.org/10.48550/arXiv.2606.10684",
            "https://arxiv.org/pdf/2606.10684",
        ),
        (
            "https://ieeexplore.ieee.org/document/11302797/",
            "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=11302797",
        ),
        ("https://example.org/paper", "https://example.org/paper"),
    ],
)
def test_known_paper_pages_resolve_to_original_pdf(url: str, expected: str) -> None:
    assert resolve_original_paper_url(url) == expected


def test_ieee_metadata_exposes_abstract_without_claiming_full_text() -> None:
    html = """
    <script>
    xplGlobal.document.metadata={"authors":[{"name":"Haechan Chong"}],
    "articleNumber":"11302797","abstract":"A graph-based failure detector.",
    "publicationDate":"February 2026","publicationTitle":"IEEE RA-L",
    "formulaStrippedArticleTitle":"Robust Task Planning","doiLink":"https://doi.org/x",
    "keywords":[{"type":"Index Terms","kwd":["Scene Graph","Robotics"]}],
    "openAccessFlag":"F","pdfPath":"/iel8/1/2/11302797.pdf"};
    </script>
    """

    metadata = extract_ieee_metadata(html)

    assert metadata is not None
    assert "접근 범위: 초록 및 서지정보만" in metadata
    assert "Robust Task Planning" in metadata
    assert "Haechan Chong" in metadata
    assert "A graph-based failure detector." in metadata
    assert "Scene Graph, Robotics" in metadata


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/admin",
        "http://127.0.0.1/secrets",
        "http://10.0.0.5/paper.pdf",
        "http://169.254.169.254/latest/meta-data",
        "file:///etc/passwd",
    ],
)
def test_research_fetch_rejects_local_and_private_urls(url: str) -> None:
    with pytest.raises(ValueError, match="public HTTP"):
        validate_public_url(url)
