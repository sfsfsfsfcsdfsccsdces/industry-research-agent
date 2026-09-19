from app.models import SourceDocument
from app.services.source_quality import normalize_url, prepare_and_deduplicate


def test_normalize_url_removes_tracking_and_fragment():
    url = "HTTPS://Example.COM:443/docs/?utm_source=test&b=2&a=1#section"
    assert normalize_url(url) == "https://example.com/docs?a=1&b=2"


def test_deduplicate_by_content_and_url():
    sources = [
        SourceDocument(title="A", url="https://a.com/x?utm_source=demo", content="相同内容 " * 30),
        SourceDocument(title="B", url="https://b.com/y", content="相同内容 " * 30),
        SourceDocument(title="C", url="https://c.com/z", content="不同内容 " * 30),
    ]
    result = prepare_and_deduplicate(sources)
    assert len(result) == 2
    assert [item.source_id for item in result] == ["S1", "S2"]
    assert all(0 <= item.credibility_score <= 1 for item in result)
