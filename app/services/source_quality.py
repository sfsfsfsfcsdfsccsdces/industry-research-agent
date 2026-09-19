from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.models import SourceDocument

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "ref", "source",
}


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    hostname = (parts.hostname or "").lower()
    port = parts.port
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        hostname = f"{hostname}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query) if k.lower() not in TRACKING_PARAMS))
    return urlunsplit((scheme, hostname, path, query, ""))


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def content_fingerprint(text: str) -> str:
    normalized = normalize_text(text)
    return hashlib.sha256(normalized[:20_000].encode("utf-8")).hexdigest()


def credibility_score(source: SourceDocument) -> float:
    domain = source.domain.lower()
    url = (source.url or "").lower()
    score = 0.52
    if source.source_type == "local":
        score = 0.72
    if any(domain.endswith(suffix) for suffix in (".gov", ".gov.cn", ".edu", ".edu.cn")):
        score = 0.93
    elif any(token in domain for token in ("github.com", "arxiv.org", "docs.", "developer.")):
        score = 0.84
    elif any(token in domain for token in ("wikipedia.org", "medium.com", "zhihu.com")):
        score = 0.60
    if url.startswith("https://"):
        score += 0.03
    if len(source.content) >= 800:
        score += 0.04
    if source.published_at:
        score += 0.02
    return round(min(score, 1.0), 3)


def prepare_and_deduplicate(sources: list[SourceDocument]) -> list[SourceDocument]:
    unique: dict[str, SourceDocument] = {}
    url_keys: set[str] = set()
    for source in sources:
        source.url = normalize_url(source.url)
        source.domain = urlsplit(source.url).hostname or "" if source.url else source.domain
        source.fingerprint = content_fingerprint(source.content)
        source.credibility_score = credibility_score(source)
        key = source.fingerprint
        if key in unique or (source.url and source.url in url_keys):
            continue
        unique[key] = source
        if source.url:
            url_keys.add(source.url)

    ordered = sorted(unique.values(), key=lambda item: (-item.credibility_score, item.title))
    for index, source in enumerate(ordered, start=1):
        source.source_id = f"S{index}"

    # Approximate cross validation by counting distinct domains that mention the same key terms.
    term_domains: dict[str, set[str]] = defaultdict(set)
    for source in ordered:
        terms = set(re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}|[\u4e00-\u9fff]{2,8}", normalize_text(source.content)))
        for term in list(terms)[:400]:
            term_domains[term].add(source.domain or source.source_type)
    for source in ordered:
        terms = set(re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}|[\u4e00-\u9fff]{2,8}", normalize_text(source.content)))
        support = max((len(term_domains[t]) for t in terms if t in term_domains), default=1)
        source.cross_validation_count = min(support, 9)
    return ordered
