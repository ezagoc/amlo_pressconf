"""Conservative Tiempo article parsing with explicit publication evidence."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from itertools import combinations
from urllib.parse import urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup, Comment

MONTHS = dict(zip("enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(), range(1, 13)))
MONTHS["setiembre"] = 9
BYLINE = re.compile(r"Por:\s*(.*?)\s+(\d{1,2})\s+(" + "|".join(MONTHS) + r")\s+(20\d{2})(?:\s+(\d{1,2}):(\d{2}))?", re.I)


def _text(node):
    return (re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() or None) if node else None


def _instagram_permalink(value):
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    parts = [part for part in parsed.path.split('/') if part]
    return value if (parsed.scheme in {'http', 'https'} and parsed.hostname in {'instagram.com', 'www.instagram.com'}
                     and len(parts) >= 2 and parts[0] in {'p', 'reel', 'tv'}) else None


def _clean_body_templates(copy, removed):
    """Remove only evidenced template leaves, retaining captions and prose."""
    def record(node, reason, href=None):
        removed.append({'reason': reason, 'text': _text(node), 'href': href})
        node.decompose()

    for embed in copy.select('blockquote.instagram-media[data-instgrm-permalink]'):
        permalink = _instagram_permalink(embed.get('data-instgrm-permalink'))
        if not permalink:
            continue
        for node in list(embed.select('div')):
            style = re.sub(r'\s+', '', node.get('style', '').casefold())
            parent_style = re.sub(r'\s+', '', node.parent.get('style', '').casefold()) if node.parent else ''
            if (_text(node) == 'Ver esta publicación en Instagram' and not node.find(['div', 'p', 'blockquote'])
                    and 'color:#3897f0' in style and 'font-family:arial' in style and 'padding-top:8px' in parent_style):
                record(node, 'instagram_view_post_ui', permalink)
        for node in list(embed.select('p')):
            anchors = node.find_all('a', href=True)
            style = re.sub(r'\s+', '', node.get('style', '').casefold())
            if (len(anchors) == 1 and not node.find(['p', 'div', 'blockquote'])
                    and _text(node) == _text(anchors[0])
                    and re.fullmatch(r'Una publicación compartida por .+ \(@[^()]+\)', _text(node) or '')
                    and 'color:#c9c8cd' in style and 'text-overflow:ellipsis' in style
                    and _instagram_permalink(anchors[0]['href'])
                    and urlparse(anchors[0]['href']).path.rstrip('/') == urlparse(permalink).path.rstrip('/')):
                record(node, 'instagram_shared_post_ui', anchors[0]['href'])

    # Only a terminal, standalone recommendation paragraph: never an enclosing
    # malformed paragraph containing real prose, or a link cited mid-article.
    for node in reversed(list(copy.find_all('p'))):
        anchors = node.find_all('a', href=True)
        if (len(anchors) != 1 or node.find(['p', 'div', 'blockquote', 'ul', 'ol', 'table'])
                or _text(node) != _text(anchors[0])
                or not re.match(r'^Podría interesarte:\s*\S', _text(anchors[0]) or '', re.I)):
            continue
        texts = list(copy.strings)
        own = list(node.strings)
        last = next((i for i in range(len(texts) - 1, -1, -1) if own and texts[i] is own[-1]), None)
        if last is not None and not any(str(value).strip() for value in texts[last + 1:]):
            record(node, 'terminal_related_article_link', anchors[0]['href'])


def _body(node, *, removed=None):
    if node is None:
        return None
    copy = BeautifulSoup(str(node), "lxml")
    for comment in copy.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()
    for el in copy.select("script,style,noscript,iframe,form,button,nav,footer,aside,.share-buttons,.publicidad-content,.ad,#sidebar"):
        el.decompose()
    _clean_body_templates(copy, removed if removed is not None else [])
    for el in copy.find_all(["p", "div", "section", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
                            "blockquote", "br", "table", "tr", "th", "td", "dl", "dt", "dd", "figcaption"]):
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


def _dates_agree(left, right, *, left_precision="second", right_precision="second"):
    if len(left) == 10 or len(right) == 10:
        return left[:10] == right[:10]
    a, b = datetime.fromisoformat(left), datetime.fromisoformat(right)
    if a.tzinfo is not None and b.tzinfo is not None:
        a, b = a.astimezone(timezone.utc), b.astimezone(timezone.utc)
    # Compare the displayed local clock when the site leaves a timezone absent;
    # never attach a guessed timezone. A discrepancy remains for manual review.
    a, b = a.replace(tzinfo=None), b.replace(tzinfo=None)
    if "minute" in (left_precision, right_precision):
        a, b = a.replace(second=0, microsecond=0), b.replace(second=0, microsecond=0)
    return a == b


def _date_precision(candidate):
    if len(candidate["value"]) == 10:
        return "date"
    if candidate["source"] == "visible_byline":
        return "minute"
    # Keep precision from the source string: fromisoformat adds :00 to a value
    # that only specified hours/minutes. Two explicit seconds must still agree.
    return "second" if re.search(r"[T ]\d{2}:?\d{2}:?\d{2}", candidate["raw"]) else "minute"


def _jsonld_objects(value):
    """Walk graphs and explicit main entities, not related/recommended entities."""
    if isinstance(value, list):
        for item in value:
            yield from _jsonld_objects(item)
    elif isinstance(value, dict):
        yield value
        if "@graph" in value:
            yield from _jsonld_objects(value["@graph"])
        if "mainEntity" in value:
            yield from _jsonld_objects(value["mainEntity"])


def _has_type(item, allowed):
    types = item.get("@type", [])
    types = [types] if isinstance(types, str) else types
    return isinstance(types, list) and any(isinstance(t, str) and t.casefold() in allowed for t in types)


def _identity_refs(value, base):
    if isinstance(value, list):
        return set().union(*(_identity_refs(v, base) for v in value)) if value else set()
    if isinstance(value, dict):
        return _identity_refs(value.get("@id"), base) | _identity_refs(value.get("url"), base)
    if not isinstance(value, str) or not value.strip() or value.startswith(("_:", "urn:")):
        return set()
    # Tiempo also emits opaque bare slugs in mainEntityOfPage.@id. Do not
    # invent an appended URL from those tokens and reject the genuine article.
    if not value.strip().startswith(("http://", "https://", "/", "#", "./", "../")):
        return set()
    resolved = urljoin(base, value.strip())
    if urlparse(resolved).scheme not in {"http", "https"}:
        return set()
    return {resolved}


def _identity_urls(value, base):
    return {urldefrag(resolved)[0].rstrip("/") for resolved in _identity_refs(value, base)}


def _current_article_json(objects, *, url, canonical):
    articles = [item for item in objects if _has_type(item, {"newsarticle", "article", "blogposting"})]
    targets = _identity_urls(url, url) | _identity_urls(canonical, url)
    main_entities = set()
    for item in objects:
        if _has_type(item, {"webpage", "itempage"}):
            page_urls = _identity_urls(item.get("url"), url) | _identity_urls(item.get("@id"), url)
            if page_urls & targets:
                main_entities |= _identity_refs(item.get("mainEntity"), url)
    matched, unscoped = [], []
    for item in articles:
        page_urls = _identity_urls(item.get("url"), url) | _identity_urls(item.get("mainEntityOfPage"), url)
        ids = _identity_refs(item.get("@id"), url)
        id_pages = {urldefrag(value)[0].rstrip("/") for value in ids}
        if page_urls & targets or ids & main_entities or (not main_entities and id_pages & targets):
            matched.append(item)
        elif not (page_urls or ids):
            unscoped.append(item)
    if matched:
        return matched, "matched_current_url", False
    if len(articles) == 1 and len(unscoped) == 1:
        return unscoped, "single_unscoped_article", False
    if unscoped:
        return [], "ambiguous_unscoped_articles", True
    return [], "no_current_article_metadata" if articles else "no_article_metadata", False


def _json_author(value):
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        return _json_author(value.get("name"))
    if isinstance(value, list):
        names = [name for item in value if (name := _json_author(item))]
        return "; ".join(dict.fromkeys(names)) or None
    return None


def _lead_text(lead, byline):
    """Retain lead prose regardless of wrappers, removing the actual byline."""
    value = _body(lead)
    if not value:
        return None
    if byline:
        # _text collapses whitespace while _body preserves paragraph breaks.
        pattern = r"\s+".join(re.escape(part) for part in byline.group(0).split())
        match = re.search(pattern, value)
        if match:
            return value[:match.start()].strip() or None
    anchor = lead.select_one("a.m-r-sm") if lead else None
    if anchor is not None:
        author = _text(anchor) or ""
        pattern = r"\bPor:\s*" + r"\s+".join(re.escape(part) for part in author.split())
        matches = list(re.finditer(pattern, value, re.I))
        if matches:
            return value[:matches[-1].start()].strip() or None
    return value


def _source_title_audit(soup, article, article_json, jsonld_errors, fields, content, body_text, canonical):
    channels = []

    def add(source, value, *, slash_placeholder=False):
        if value is None:
            status = 'absent'
        elif not isinstance(value, str):
            status = 'unassessable_value'
        elif not value.strip():
            status = 'empty'
        elif slash_placeholder and value.strip() == '/':
            status = 'observed_meta_title_placeholder'
        else:
            status = 'informative'
        channels.append({'channel': source, 'value': value, 'status': status})

    h1s = article.select(':scope > header > h1')
    recognized_empty_h1 = bool(h1s) and all(not (_text(node) or '') for node in h1s)
    for selector, scope, label in [('h1', article, 'current_article.h1'), ('title', soup, 'document.title'),
                                  (':scope > header h2, :scope > header h3, :scope > header h4, :scope > header h5, :scope > header h6, :scope > header [itemprop~="headline"], :scope > header [data-headline], :scope > header .headline', article, 'current_header.potential_headline')]:
        nodes = scope.select(selector)
        if not nodes:
            add(label, None)
        for index, node in enumerate(nodes):
            add(f'{label}[{index}]', node.get_text(' ', strip=True))
            for attr in ('content', 'data-headline'):
                if node.has_attr(attr):
                    add(f'{label}[{index}].{attr}', node.get(attr))
    for key in ('title', 'og:title', 'twitter:title'):
        metas = [node for node in soup.find_all('meta') if any(str(node.get(attr, '')).casefold() == key for attr in ('name', 'property'))]
        if not metas:
            add('meta.' + key, None)
        for index, node in enumerate(metas):
            add(f'meta.{key}[{index}]', node.get('content'), slash_placeholder=(key == 'title' and str(node.get('name', '')).casefold() == 'title'))
    for index, item in enumerate(article_json):
        for key in ('headline', 'name', 'alternativeHeadline'):
            add(f'current_jsonld[{index}].{key}', item.get(key))
    if not article_json:
        add('current_jsonld.headline', None)
    all_empty = not jsonld_errors and all(item['status'] in {'absent', 'empty', 'observed_meta_title_placeholder'} for item in channels)
    conditions = {
        'recognized_empty_h1': recognized_empty_h1,
        'all_title_channels_empty': all_empty,
        'recognized_nonempty_body': content is not None and bool(body_text),
        'explicit_valid_canonical': bool(canonical and canonical.get('href') and fields['canonical_url']),
        'verified_publication_date': bool(fields['date_published'] and fields['publication_date_source'] and not fields['date_conflict']),
        'no_other_source_error': fields['source_specific_error'] is None,
    }
    status = ('confirmed_source_empty' if fields['title'] is None and all(conditions.values())
              else 'title_present' if fields['title'] else 'unconfirmed_missing')
    fields['source_title_status'] = status
    fields['source_title_evidence'] = json.dumps({'schema_version': 1, **conditions, 'channels': channels,
                                                'jsonld_parse_errors': jsonld_errors}, ensure_ascii=False)


def tiempo_fields(html: str, *, url: str) -> dict[str, object]:
    soup = BeautifulSoup(html, "lxml")
    article = soup.select_one("article#article-post")
    fields = dict.fromkeys(("canonical_url", "title", "summary", "main_text", "authors", "date", "date_published", "date_modified", "topic", "section", "language", "publication_date_source", "publication_date_evidence", "date_conflict", "author_source", "body_selector", "source_specific_error", "media_embeds", "jsonld_article_selection", "source_title_status", "source_title_evidence", "removed_body_elements", "related_links"))
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
    objects, jsonld_errors = [], []
    for index, node in enumerate(soup.select('script[type="application/ld+json"]')):
        try:
            parsed = json.loads(node.string or node.get_text(), strict=False)
        except (ValueError, TypeError):
            jsonld_errors.append({'script_index': index, 'error': 'unparseable_jsonld'})
            continue
        objects.extend(_jsonld_objects(parsed))
    article_json, selection, ambiguous = _current_article_json(objects, url=url, canonical=fields["canonical_url"])
    fields["jsonld_article_selection"] = selection
    if ambiguous and not fields["source_specific_error"]:
        fields["source_specific_error"] = "ambiguous_jsonld_article"
    ld = article_json[0] if article_json else {}

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
        elif (author := _json_author(ld.get("author"))):
            fields["authors"], fields["author_source"] = author, "jsonld.author"
    for item in article_json:
        published = _iso(item.get("datePublished"))
        if published:
            candidates.append({"source": "jsonld.datePublished", "raw": item["datePublished"], "value": published})
    for name in ("og:article:published_time", "article:published_time", "datePublished"):
        for meta in soup.find_all("meta"):
            if meta.get("property", meta.get("name", "")).casefold() == name.casefold():
                value = _iso(meta.get("content"))
                if value:
                    candidates.append({"source": name, "raw": meta["content"], "value": value})
    if candidates:
        if any(not _dates_agree(a["value"], b["value"], left_precision=_date_precision(a), right_precision=_date_precision(b))
               for a, b in combinations(candidates, 2)):
            fields["date_conflict"] = json.dumps(candidates, ensure_ascii=False)
            fields["source_specific_error"] = "conflicting_publication_dates"
        else:
            # Retain genuine time precision; a date-only tag does not mean midnight.
            ranks = {"date": 0, "minute": 1, "second": 2}
            best_precision = max(ranks[_date_precision(c)] for c in candidates)
            precise = [c for c in candidates if ranks[_date_precision(c)] == best_precision]
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
    fields["summary"] = _lead_text(lead, byline)
    content = article.select_one(".complementos-container")
    if content is None:
        fields["source_specific_error"] = "unrecognized_tiempo_body"
    removed = []
    body_text = _body(content, removed=removed)
    fields["main_text"] = "\n".join(x for x in (fields["summary"], body_text) if x) or None
    fields['removed_body_elements'] = json.dumps(removed, ensure_ascii=False)
    fields['related_links'] = json.dumps([{'url': item['href'], 'text': item['text']} for item in removed if item['reason'] == 'terminal_related_article_link'], ensure_ascii=False)
    fields["body_selector"] = "article#article-post > blockquote + .complementos-container"
    embed_urls = []
    if content:
        embed_urls.extend(n["src"] for n in content.select("iframe[src]"))
        embed_urls.extend(n["cite"] for n in content.select("blockquote[cite]"))
        embed_urls.extend(link for n in content.select('blockquote.instagram-media[data-instgrm-permalink]')
                          if (link := _instagram_permalink(n.get('data-instgrm-permalink'))))
        for node in content.select("blockquote.twitter-tweet a[href], blockquote.twitter-video a[href]"):
            if re.search(r"/(?:status|statuses)/\d+", node["href"]):
                embed_urls.append(node["href"])
    fields["media_embeds"] = json.dumps(list(dict.fromkeys(embed_urls)), ensure_ascii=False)
    fields["topic"] = fields["section"] = _text(article.select_one("header .breadcrumb li.active a"))
    _source_title_audit(soup, article, article_json, jsonld_errors, fields, content, body_text, canonical)
    return fields
