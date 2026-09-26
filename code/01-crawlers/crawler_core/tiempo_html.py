"""Conservative Tiempo article parsing with explicit publication evidence."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from itertools import combinations
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Comment

MONTHS = dict(zip("enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(), range(1, 13)))
MONTHS["setiembre"] = 9
BYLINE = re.compile(r"Por:\s*(.*?)\s+(\d{1,2})\s+(" + "|".join(MONTHS) + r")\s+(20\d{2})(?:\s+(\d{1,2}):(\d{2}))?", re.I)


def _text(node):
    return (re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() or None) if node else None


def _body(node):
    if node is None:
        return None
    copy = BeautifulSoup(str(node), "lxml")
    for comment in copy.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()
    for el in copy.select("script,style,noscript,iframe,form,button,nav,footer,aside,.share-buttons,.publicidad-content,.ad,#sidebar"):
        el.decompose()
    for el in copy.find_all(["p", "div", "li", "ul", "ol", "h2", "h3", "h4", "blockquote", "br"]):
        el.insert_before("\n")
        el.insert_after("\n")
    lines = [re.sub(r"\s+", " ", x).strip() for x in copy.get_text().splitlines()]
    return "\n".join(x for x in lines if x) or None


def _iso(raw):
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        value = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        if value.year < 1900:
            return None
        return value.date().isoformat() if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw.strip()) else value.isoformat()
    except ValueError:
        return None


def valid_article_url(value):
    if not value:
        return False
    p = urlparse(value)
    parts = [part for part in p.path.split("/") if part]
    return p.scheme in {"http", "https"} and p.hostname in {"tiempo.com.mx", "www.tiempo.com.mx"} and len(parts) >= 2 and "//" not in p.path


def _dates_agree(left, right):
    if len(left) == 10 or len(right) == 10:
        return left[:10] == right[:10]
    a, b = datetime.fromisoformat(left), datetime.fromisoformat(right)
    if a.tzinfo is not None and b.tzinfo is not None:
        a, b = a.astimezone(timezone.utc), b.astimezone(timezone.utc)
    # Compare the displayed local clock when the site leaves a timezone absent;
    # never attach a guessed timezone. A discrepancy remains for manual review.
    return a.replace(tzinfo=None, second=0, microsecond=0) == b.replace(tzinfo=None, second=0, microsecond=0)


def tiempo_fields(html: str, *, url: str) -> dict[str, object]:
    soup = BeautifulSoup(html, "lxml")
    article = soup.select_one("article#article-post")
    fields = dict.fromkeys(("canonical_url", "title", "summary", "main_text", "authors", "date", "date_published", "date_modified", "topic", "section", "language", "publication_date_source", "publication_date_evidence", "date_conflict", "author_source", "body_selector", "source_specific_error", "media_embeds"))
    fields["language"] = soup.html.get("lang") if soup.html else None
    title = _text(article.select_one("h1") if article else soup.select_one("h1"))
    fields["title"] = title
    if title and "ocurrió un error al procesar la noticia" in title.casefold():
        fields["source_specific_error"] = "soft_error_page"
        return fields
    if article is None:
        fields["source_specific_error"] = "unrecognized_tiempo_layout"
        return fields
    canonical = soup.select_one('link[rel="canonical"]')
    canonical_url = urljoin(url, canonical.get("href", "")) if canonical else url
    if valid_article_url(canonical_url):
        fields["canonical_url"] = canonical_url
    else:
        fields["source_specific_error"] = "invalid_article_canonical"

    # This site emits literal newlines inside JSON strings; strict=False permits
    # those control characters without executing or inventing any content.
    ld = {}
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            parsed = json.loads(node.string or node.get_text(), strict=False)
        except (ValueError, TypeError):
            continue
        for item in parsed if isinstance(parsed, list) else [parsed]:
            if isinstance(item, dict) and isinstance(item.get("@type"), str) and item["@type"] in {"NewsArticle", "Article", "BlogPosting"}:
                ld = item
                break
        if ld:
            break

    lead = article.find("blockquote", recursive=False)
    byline = BYLINE.search(_text(lead) or "")
    candidates = []
    visible_date = None
    if byline:
        author, day, month, year, hour, minute = byline.groups()
        try:
            visible_date = datetime(int(year), MONTHS[month.casefold()], int(day), int(hour or 0), int(minute or 0))
            candidates.append({"source": "visible_byline", "raw": byline.group(0), "value": visible_date.isoformat() if hour else visible_date.date().isoformat()})
        except ValueError:
            fields["source_specific_error"] = "invalid_publication_date"
        fields["authors"] = author.strip() or None
        fields["author_source"] = "visible_byline" if author.strip() else None
    if fields["authors"] is None:
        author = _text(lead.select_one("a.m-r-sm")) if lead else None
        if author:
            fields["authors"], fields["author_source"] = author, "visible_byline"
        elif isinstance(ld.get("author"), dict) and ld["author"].get("name"):
            fields["authors"], fields["author_source"] = ld["author"]["name"], "jsonld.author"
    published = _iso(ld.get("datePublished"))
    if published:
        candidates.append({"source": "jsonld.datePublished", "raw": ld["datePublished"], "value": published})
    for name in ("og:article:published_time", "article:published_time", "datePublished"):
        for meta in soup.find_all("meta"):
            if meta.get("property", meta.get("name", "")).casefold() == name.casefold():
                value = _iso(meta.get("content"))
                if value:
                    candidates.append({"source": name, "raw": meta["content"], "value": value})
    if candidates:
        if any(not _dates_agree(a["value"], b["value"]) for a, b in combinations(candidates, 2)):
            fields["date_conflict"] = json.dumps(candidates, ensure_ascii=False)
            fields["source_specific_error"] = "conflicting_publication_dates"
        else:
            # Retain genuine time precision; a date-only tag does not mean midnight.
            precise = [c for c in candidates if len(c["value"]) > 10] or candidates
            chosen = next((c for c in precise if c["source"] == "jsonld.datePublished"), precise[0])
            fields["date_published"] = fields["date"] = chosen["value"]
            fields["publication_date_source"] = chosen["source"]
    fields["publication_date_evidence"] = json.dumps(candidates, ensure_ascii=False)
    fields["date_modified"] = _iso(ld.get("dateModified"))
    if not fields["date_modified"]:
        meta = soup.select_one('meta[property="article:modified_time"]')
        fields["date_modified"] = _iso(meta.get("content")) if meta else None

    # Preserve lead + body prose, never the adjacent byline or sidebar. Repeated
    # genuine paragraphs are not silently deduplicated. No 500-character cutoff.
    lead_parts = []
    for p in lead.find_all("p", recursive=False) if lead else []:
        value = _body(p)
        if value:
            match = BYLINE.search(value)
            if match:
                value = value[:match.start()].strip()
        if value:
            lead_parts.append(value)
    fields["summary"] = "\n".join(x for x in lead_parts if x) or None
    content = article.select_one(".complementos-container")
    if content is None:
        fields["source_specific_error"] = "unrecognized_tiempo_body"
    fields["main_text"] = "\n".join(x for x in (fields["summary"], _body(content)) if x) or None
    fields["body_selector"] = "article#article-post > blockquote p + .complementos-container"
    embed_urls = []
    if content:
        embed_urls.extend(n["src"] for n in content.select("iframe[src]"))
        embed_urls.extend(n["cite"] for n in content.select("blockquote[cite]"))
        for node in content.select("blockquote.twitter-tweet a[href], blockquote.twitter-video a[href]"):
            if re.search(r"/(?:status|statuses)/\d+", node["href"]):
                embed_urls.append(node["href"])
    fields["media_embeds"] = json.dumps(list(dict.fromkeys(embed_urls)), ensure_ascii=False)
    fields["topic"] = fields["section"] = _text(article.select_one("header .breadcrumb li.active a"))
    return fields
