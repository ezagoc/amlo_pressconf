"""Kevin: strict static-source gap evidence; never repair or accept an article.

No request URL/sample/date whitelist is used. Known template fingerprints cover
only inspected inert DOM comments and site scripts, not whole response hashes.
An unfamiliar feature rejects the exemption. External scripts are not executed;
the finding is limited to the saved static response, never historical absence.
"""
from __future__ import annotations

import hashlib
import html as html_entities
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Comment

RULE_VERSION = 'tiempo-verified-static-empty-shell-v5'
FEATURE_PATH = Path(__file__).with_name('tiempo_empty_shell_features.json')
_FEATURE_BYTES = FEATURE_PATH.read_bytes()
FEATURES = json.loads(_FEATURE_BYTES)
FEATURE_SHA256 = hashlib.sha256(_FEATURE_BYTES).hexdigest()
CLASSIFICATION = 'source_unavailable_body_in_saved_response'
_ALLOWED_FLAGS = {'missing_body', 'unexplained_result_error', 'suspicious_very_short_body_review_only'}
_REPRESENTATION_FLAGS = {'visible_title_difference','source_title_metadata_disagreement'}
_EXTERNAL = {'https://static.tiempo.com.mx/assets/htmx.min-1.js',
             'https://static.tiempo.com.mx/assets/periodico/application.js'}
_MONTHS = ('Enero Febrero Marzo Abril Mayo Junio Julio Agosto Septiembre Octubre Noviembre Diciembre').split()
_CSS = '.video-container { max-width: 100%; max-height: 600px; margin: 0 auto; display: block; }'


def _norm(text):
    return re.sub(r'\s+', ' ', str(text or '')).strip()


def _title(text):
    # DOM attributes/text and native values have already been HTML-decoded.
    return _norm(text)


def _jsonld_title(text):
    # Only raw JSON-LD has the observed remaining source entity representation.
    return _norm(html_entities.unescape(str(text or '')))


def _source_jsonld_title(text, expected):
    # Preserve a literal entity spelling when the independent DOM/native
    # channels use that same spelling. Decode once only as a fallback.
    value = _norm(text)
    return value if value == _title(expected) else _jsonld_title(value)


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _identity(url):
    p = urlsplit(url or '')
    if p.scheme not in {'http', 'https'} or p.hostname not in {'tiempo.com.mx', 'www.tiempo.com.mx'} or p.username or p.password or p.query or p.fragment or p.port not in (None, 80, 443):
        raise ValueError('unrecognized_article_identity')
    parts = p.path.strip('/').split('/')
    if len(parts) != 2 or not all(parts) or parts[0] not in {'noticia', *FEATURES['official_sections'], *FEATURES['legacy_sections']}:
        raise ValueError('unrecognized_article_route')
    return parts[-1]


def _inline_key(text):
    # Only three exact literal slots inside the otherwise fixed poll script.
    text = re.sub(r"setRequestHeader\('X-CSRFToken','[A-Za-z0-9]+'\)",
                  "setRequestHeader('X-CSRFToken','CSRF_SLOT')", text)
    text = re.sub(r"'csrf_token':\s*'[A-Za-z0-9]+'", "'csrf_token': 'CSRF_SLOT'", text)
    text = re.sub(r"'encuestaid':\s*'\d+'", "'encuestaid': 'POLL_SLOT'", text)
    return _sha(_norm(text).encode())


def article_structure(article, row):
    """Hierarchy and attributes, normalizing only verified metadata/ad slots."""
    nodes = [article, *article.find_all(True)]
    positions = {id(node): i for i, node in enumerate(nodes)}
    result = []
    title_words = set(_title(row['title']).lower().split())
    for node in nodes:
        attrs = dict(node.attrs)
        share = node.find_parent('ul', class_='share-buttons')
        if share and node.name == 'a':
            # The inspected source has malformed unquoted title-word attributes.
            for key in list(attrs):
                if key not in {'href','title','target','onclick','data-link','data-text','class'} and attrs[key] == '' and html_entities.unescape(key) in title_words:
                    del attrs[key]
            for key in ('title','data-text'):
                if _title(attrs.get(key)) == _title(row['title']):
                    attrs[key] = 'TITLE_SLOT'
            if attrs.get('data-link') == row['canonical_url']:
                attrs['data-link'] = 'CANONICAL_SLOT'
            for prefix in ('https://twitter.com/intent/tweet?source=&text=', 'mailto:?subject=&body='):
                if _norm(attrs.get('href')) == _norm(prefix + row['title']):
                    attrs['href'] = prefix + 'TITLE_SLOT'
        if node.name == 'a' and re.fullmatch(r'/hits/\d+', attrs.get('href','')):
            attrs['href'] = 'AD_CLICK_SLOT'
        if node.name == 'img' and attrs.get('src','').startswith('https://ads.tiempo.com.mx/uploads/banners/'):
            attrs['src'] = 'AD_IMAGE_SLOT'
        if node.name == 'a' and node.find_parent('ol', class_='breadcrumb'):
            route = urlsplit(row['canonical_url']).path.strip('/').split('/')[0]
            section_label = FEATURES['official_sections'].get(route) or FEATURES['legacy_sections'].get(route)
            if attrs == {'href':'/'+route+'/'} and _norm(node.get_text()) == section_label:
                attrs['href'] = 'SECTION_SLOT'
        result.append([node.name, positions.get(id(node.parent), -1), attrs])
    return result


def recommendation_structure(rest, row):
    """Known post-article headline cards, never arbitrary sibling prose."""
    nodes = [rest, *rest.find_all(True)]
    positions = {id(node): i for i, node in enumerate(nodes)}
    result = []
    for node in nodes:
        attrs = dict(node.attrs)
        if node.name == 'a' and attrs.get('href','').startswith('/'):
            path = attrs['href'].strip('/').split('/')
            if len(path) != 2 or not all(path) or path[-1] == _identity(row['url']):
                raise ValueError('unrecognized_recommendation_identity')
            attrs['href'] = 'RECOMMENDATION_URL_SLOT'
        if node.name == 'img':
            if not attrs.get('src','').startswith('https://static.tiempo.com.mx/uploads/imagen/imagen/'):
                raise ValueError('unrecognized_recommendation_image')
            attrs['src'] = 'RECOMMENDATION_IMAGE_SLOT'
        result.append([node.name, positions.get(id(node.parent), -1), attrs])
    return result


def _known_poll_percentage_comment(comment, value):
    """Recognize only a redundant percentage label in the sidebar poll UI.

    The numeric slot varies with votes; it is not article evidence. Requiring
    its actual DOM position and four equal labels prevents a global comment
    waiver or acceptance of prose/embeds hidden in other source locations.
    """
    if comment is None or not 0 <= float(value) <= 100:
        return False
    bar = comment.parent
    progress = bar.parent
    result = progress.parent
    poll = result.parent
    sidebar = poll.find_parent(id='sidebar')
    if (bar.name != 'div' or set(bar.attrs) != {'class','role','aria-valuenow','aria-valuemin','style'}
            or bar.get('class') != ['progress-bar'] or bar.get('role') != 'progressbar'
            or bar.get('aria-valuenow') != value or bar.get('aria-valuemin') != '0'
            or not re.fullmatch(r'width: '+re.escape(value)+r'%; height:20px; background-color: #(439646|009688|f44336);', _norm(bar.get('style')))):
        return False
    if (progress.name != 'div' or progress.attrs != {'class':['progress'],'style':'height:20px;'}
            or result.name != 'div' or result.attrs != {'id':'result','class':['bs-chart-container','collapse'],'style':'width: 88%;padding: 15px 0;'}
            or poll.name != 'div' or set(poll.attrs) != {'id','class'} or poll.get('class') != ['encuesta']
            or re.fullmatch(r'aplicacion-encuesta\d+-container', poll.get('id','')) is None
            or sidebar is None or sidebar.name != 'div' or sidebar.attrs != {'id':'sidebar'}
            or poll.find_parent('article') is not None or poll.find_parent(id='main') is not None):
        return False
    children = bar.find_all(True, recursive=False)
    if len(children) != 1 or children[0].name != 'span' or children[0].attrs != {'class': []} or children[0].find(True):
        return False
    if _norm(children[0].get_text()) != value+'%':
        return False
    comments = bar.find_all(string=lambda node:isinstance(node,Comment))
    return (len(comments) == 1 and comments[0] is comment
            and all(isinstance(node,Comment) or not _norm(node) for node in bar.find_all(string=True,recursive=False)))


def _known_comment(text, author, published, comment=None):
    text = _norm(text)
    percentage = re.fullmatch(r'span class="value">(\d{1,3}(?:\.\d+)?)% </span', text)
    if percentage:
        # Check contextual numeric comments before legacy fingerprints too.
        return _known_poll_percentage_comment(comment, percentage.group(1))
    if _sha(text.encode()) in FEATURES['known_comment_sha256']:
        return True
    if re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', text):
        return True  # Inspected inert tracking marker, no markup or prose.
    if re.fullmatch(r'<p class="current-date"><i class="fa fa-calendar"></i> (?:Lunes|Martes|Miércoles|Jueves|Viernes|Sábado|Domingo) \d{1,2} (?:' + '|'.join(_MONTHS) + r') \d{4}', text):
        return True  # Site-header display date; not publication evidence.
    d = datetime.fromisoformat(published.replace('Z', '+00:00'))
    date = f'{d.day:02d} {_MONTHS[d.month-1]} {d.year}'
    expected = (
        '<footer style="background-color: transparent;"><i class="fa fa-user text-muted" style="color: #444"></i> Por: '
        f'<a href="" class="m-r-sm"><strong>{author}</strong></a><br/></footer> '
        '<footer style="background-color: transparent;"><i class="fa fa-calendar text-muted" style="color: #444"></i> '
        f'{date}<br/></footer> '
        '<footer style="background-color: transparent;"><i class="fa fa-clock-o text-muted" style="color: #444"></i> '
        f'{d.hour:02d} {d.minute:02d}<br/></footer>')
    return text == expected


def classify_empty_article_shell(row, html_bytes, response_metadata, source_check):
    """Return derived evidence only. Missing/malformed inputs fail closed.

    Caller must supply the bound completed fetch_attempts.response_json. Native
    payload/diagnostic flags are neither changed nor returned as successful.
    """
    reasons = []
    evidence = {'scope': 'saved_static_response_only', 'native_result_unchanged': True,
                'human_approval': False, 'article_acceptance': False,
                'research_status': 'NEEDS_JOAQUIN_REVIEW',
                'feature_sha256': FEATURE_SHA256, 'explained_representation_flags': []}

    def need(ok, reason):
        if not ok:
            reasons.append(reason)

    try:
        need(_sha(FEATURE_PATH.read_bytes()) == FEATURE_SHA256, 'feature_file_changed_since_import')
        need(isinstance(html_bytes, bytes), 'raw_bytes_required')
        if not isinstance(html_bytes, bytes):
            raise ValueError('raw_bytes_required')
        evidence['snapshot_sha256'] = _sha(html_bytes)
        need(evidence['snapshot_sha256'] == row.get('snapshot_sha256') == source_check.get('snapshot_sha256'), 'snapshot_binding_mismatch')
        need(source_check.get('sample_id') == row.get('sample_id') and source_check.get('url') == row.get('url'), 'rowcheck_identity_mismatch')
        need(row.get('error') == 'missing_body' and row.get('qa_status') == 'error' and row.get('main_text') is None and row.get('summary') is None, 'not_native_null_missing_body')
        need(not row.get('source_specific_error') and not row.get('date_conflict') and not source_check.get('critical_flags'), 'source_identity_date_or_access_flag')
        observed_representation_flags = set(source_check.get('automatic_flags', [])) & _REPRESENTATION_FLAGS
        need(set(source_check.get('automatic_flags', [])) <= _ALLOWED_FLAGS | _REPRESENTATION_FLAGS and 'missing_body' in source_check.get('automatic_flags', []), 'unrelated_source_check_flag')
        need(not source_check.get('source_markup_warnings') and not source_check.get('outside_body_scope_evidence'), 'unexplained_source_markup')
        need(not source_check.get('recognized_video_only'), 'recognized_video_uses_existing_rule')
        need(row.get('status') == 200 and response_metadata.get('status') == 200 and response_metadata.get('curl_exit_code') == 0 and response_metadata.get('error') is None and response_metadata.get('body_text_limit_exceeded') is False, 'incomplete_or_failed_transport')
        need(response_metadata.get('final_url') == row.get('final_url') == row.get('url'), 'unexpected_transport_redirect')
        need('html' in str(response_metadata.get('content_type', '')).lower() and 'html' in str(row.get('content_type', '')).lower(), 'non_html_response')
        need(response_metadata.get('body_encoding', '').lower() == 'utf-8', 'unknown_response_encoding')
        need(all(re.search(r'(?:^|;)\s*charset\s*=\s*[\"\']?utf-8(?:[\"\']?(?:;|\s*$))', str(v), re.I) for v in [row.get('content_type'), response_metadata.get('content_type')]), 'unbound_utf8_content_type')
        html = html_bytes.decode('utf-8', errors='strict')
        need(html.rstrip().lower().endswith('</html>') and '</body>' in html.lower(), 'incomplete_html_envelope')
        need(not re.search(r'cf-chl-|captcha|access denied|verify you are human|checking your browser', html, re.I), 'access_challenge_marker')
        slug = _identity(row.get('url'))
        need(_identity(row.get('canonical_url')) == slug and _identity(row.get('final_url')) == slug, 'article_slug_identity_mismatch')
        published = row.get('date_published')
        d = datetime.fromisoformat(published.replace('Z', '+00:00'))
        need(bool(row.get('title')) and bool(row.get('authors')), 'missing_identity_metadata')
        need(row.get('publication_date_source') in {'jsonld.datePublished', 'visible_byline', 'og:article:published_time', 'article:published_time', 'datePublished'}, 'unverified_publication_source')
        s = BeautifulSoup(html, 'html.parser')
        need(not s.select('meta[http-equiv],base'), 'unknown_http_equiv_instruction')
        # Metadata can contain otherwise omitted prose/media, so it is evidence,
        # not merely presentation. Only inspected empty/headline/site slots fit.
        placeholder_image = 'https://static.tiempo.com.mx/uploads/imagen/imagen/0/principal_'
        for meta in s.find_all('meta'):
            key = str(meta.get('property') or meta.get('name') or meta.get('itemprop') or '').lower()
            value = _norm(meta.get('content'))
            if 'description' in key:
                allowed = {''}
                if key == 'og:description':
                    allowed.add(_norm(row['title']))
                if key == 'description':
                    allowed.add('Tiempo - La Noticia Digital.')
                need(value in allowed, 'metadata_contains_unexplained_prose')
            if key in {'og:image','twitter:image','twitter:card','image','image_src','thumbnail','thumbnailurl'}:
                need(value == placeholder_image, 'metadata_contains_article_media')
            elif key.startswith(('og:image:', 'twitter:image:')):
                need((key, value) in {('og:image:width','1200'),('og:image:width','770'),
                    ('og:image:height','675'),('og:image:height','443')}, 'unknown_image_metadata')
            elif any(word in key for word in ('video','audio','player','image','thumbnail')):
                need(False, 'unknown_media_metadata')
            if key in {'articlebody','text','transcript'}:
                need(not value, 'metadata_contains_unexplained_prose')
        need(not s.select('link[rel="image_src"],link[as="image"],link[as="video"],link[as="audio"]'), 'unknown_link_media')
        articles = s.select('article#article-post')
        need(len(articles) == 1 and len(s.find_all('article')) == 1, 'ambiguous_article_structure')
        if len(articles) != 1:
            raise ValueError('missing_unique_article')
        a = articles[0]
        route = urlsplit(row['canonical_url']).path.strip('/').split('/')[0]
        official_section = FEATURES['official_sections'].get(route)
        legacy_section = FEATURES['legacy_sections'].get(route)
        section = official_section or legacy_section
        breadcrumbs = a.select('header ol.breadcrumb li.active a')
        navs = s.select('nav#menu')
        navlinks = navs[0].select('a[href="/'+route+'/"]') if len(navs) == 1 else []
        navigation_bound = (len(navlinks) == 1 and _norm(navlinks[0].get_text()) == section)
        # A source-read legacy category may no longer be in current navigation.
        # Its label is classification evidence only, never playable-media proof.
        legacy_bound = legacy_section is not None and len(navs) == 1 and (not navlinks or navigation_bound)
        need(section is not None and len(breadcrumbs) == 1
             and breadcrumbs[0].attrs == {'href':'/'+route+'/'}
             and _norm(breadcrumbs[0].get_text()) == section
             and (navigation_bound if official_section else legacy_bound)
             and row.get('section') == section, 'unverified_source_section_identity')
        evidence['source_section_identity'] = {'canonical_route':route,'source_label':section,
            'basis':'current_navigation' if official_section else 'bound_legacy_source_category',
            'category_is_playable_video_evidence':False}
        for alternate in s.select('[itemprop~="articleBody"],.article-content,.article-body,#article-body,#article-content'):
            need(alternate is a or any(parent is a for parent in alternate.parents), 'alternate_article_body_outside_primary_scope')
        need(','.join(x.name for x in a.find_all(True)) == FEATURES['article_tag_shape'], 'unknown_article_tag_structure')
        structure = article_structure(a, row)
        need(structure == FEATURES.get('article_structure'), 'unknown_article_attributes_or_hierarchy')
        headers, leads, bodies = a.select('header h1'), a.select('blockquote'), a.select('.complementos-container')
        need(len(headers) == len(leads) == len(bodies) == 1, 'unknown_lead_or_body_structure')
        if len(headers) != 1 or len(leads) != 1 or len(bodies) != 1:
            raise ValueError('missing_unique_title_lead_body')
        title, lead, body = headers[0], leads[0], bodies[0]
        need(_title(title.get_text(' ', strip=True)) == _title(row['title']), 'title_identity_mismatch')
        need(_title(s.title.get_text()) == _title(row['title']) if s.title else False, 'document_title_mismatch')
        channels = s.select('meta[property="og:title"],meta[name="twitter:title"]')
        need(bool(channels) and all(_title(x.get('content')) == _title(row['title']) for x in channels), 'title_metadata_mismatch')
        canonical = s.select('link[rel="canonical"]')
        need(len(canonical) == 1 and canonical[0].get('href') == row['canonical_url'], 'canonical_source_mismatch')
        ogurls = s.select('meta[property="og:url"]')
        need(bool(ogurls) and all(_identity(x.get('content')) == slug for x in ogurls), 'og_identity_mismatch')
        expected_byline = f'Por: {row["authors"]} {d.day:02d} {_MONTHS[d.month-1]} {d.year} {d.hour:02d}:{d.minute:02d}'
        need(_norm(lead.get_text(' ', strip=True)) == expected_byline and all(not _norm(x.get_text()) for x in lead.find_all('p')), 'lead_prose_or_date_author_mismatch')
        times = s.select('meta[property="og:article:published_time"],meta[property="article:published_time"]')
        need(bool(times) and all(x.get('content') == published for x in times), 'publication_metadata_mismatch')
        ld = s.select('script[type="application/ld+json"]')
        need(len(ld) == 1, 'ambiguous_jsonld')
        if len(ld) != 1:
            raise ValueError('missing_single_jsonld')
        j = json.loads(ld[0].get_text(), strict=False)
        allowed_ld = {'@context', '@type', 'headline', 'datePublished', 'dateModified', 'description', 'keywords', 'articleSection', 'articleBody', 'isAccessibleForFree', 'publisher', 'mainEntityOfPage', 'author', 'image'}
        need(isinstance(j, dict) and set(j) <= allowed_ld and j.get('@type') == 'NewsArticle', 'unknown_jsonld_structure')
        need(isinstance(j.get('articleBody'), str) and not _norm(j['articleBody']) and not _norm(j.get('description')), 'jsonld_contains_prose')
        need(_source_jsonld_title(j.get('headline'),row['title']) == _title(row['title']) and j.get('datePublished') == published and j.get('dateModified') == row.get('date_modified'), 'jsonld_identity_or_date_mismatch')
        if observed_representation_flags:
            from crawler_core.tiempo_continuous_source import fields_digest
            need(source_check.get('fields_sha256') == fields_digest(row), 'representation_native_field_binding_mismatch')
            need(response_metadata.get('body_encoding_source') == 'http_charset', 'representation_encoding_evidence_missing')
            old = BeautifulSoup(html_bytes, 'html.parser')
            old_heading = old.select('article#article-post header h1')
            old_ld = old.select('script[type="application/ld+json"]')
            need(len(old_heading) == len(old_ld) == 1, 'unreproducible_native_title_structure')
            reproduced = set()
            if len(old_heading) == len(old_ld) == 1:
                if _norm(old_heading[0].get_text(' ',strip=True)) != _norm(row['title']):
                    reproduced.add('visible_title_difference')
                old_json = json.loads(old_ld[0].get_text(),strict=False)
                # Exactly reproduce the unchanged native check, including its
                # own single unescape. This is explanatory evidence only.
                old_channels = [_jsonld_title(x.get('content')) for x in old.select('meta[property="og:title"],meta[name="twitter:title"]')]
                old_channels += [_jsonld_title(old.title.get_text())] if old.title else []
                old_channels += [_jsonld_title(old_json.get('headline'))]
                if any(v and v != _jsonld_title(row['title']) for v in old_channels):
                    reproduced.add('source_title_metadata_disagreement')
            strict_channels = [_title(title.get_text(' ',strip=True)),_title(s.title.get_text()) if s.title else '',_source_jsonld_title(j.get('headline'),row['title'])]
            strict_channels += [_title(x.get('content')) for x in channels]
            strict_agrees = all(v == _title(row['title']) for v in strict_channels)
            proven = strict_agrees and reproduced == observed_representation_flags and old.original_encoding not in (None,'utf-8','utf8')
            need(proven, 'unexplained_title_representation_flags')
            evidence['representation_validation'] = {'strict_utf8_channels_agree':strict_agrees,
                'old_byte_parser_encoding':old.original_encoding,'reproduced_native_flags':sorted(reproduced),
                'native_fields_sha256':source_check.get('fields_sha256'),'raw_jsonld_entity_decode_passes':int(_norm(j.get('headline')) != _title(row['title'])),
                'additional_dom_entity_decode_passes':0}
            if proven:
                evidence['explained_representation_flags'] = sorted(observed_representation_flags)
        author = j.get('author')
        need(j.get('mainEntityOfPage') == {'@type': 'WebPage', '@id': slug}
             and isinstance(author, dict) and set(author) == {'@type','name'}
             and author.get('@type') == 'Person' and isinstance(author.get('name'), str)
             and _norm(author['name']) == _norm(row['authors']), 'jsonld_entity_or_author_mismatch')
        need(j.get('isAccessibleForFree') is True, 'unconfirmed_access')
        publisher = j.get('publisher')
        expected_publisher = {'@type':'NewsMediaOrganization','name':'Tiempo La Noticia Digital',
            'url':'https://www.tiempo.com.mx','sameAs':['https://www.facebook.com/tiempo','https://www.twitter.com/tiempo_mx','https://www.instagram.com/tiempo.com.mx','https://www.youtube.com/@tiempotv'],
            'logo':{'@type':'ImageObject','url':'https://static.tiempo.com.mx/uploads/configuracion_periodico/imagen/1/logo-tiempo.png','height':110,'width':330}}
        need(publisher == expected_publisher and j.get('@context') == 'https://schema.org' and not _norm(j.get('keywords')) and not _norm(j.get('articleSection')), 'unknown_publisher_or_extra_jsonld_content')
        image = j.get('image')
        need(isinstance(image, dict) and image.get('url') == 'https://static.tiempo.com.mx/uploads/imagen/imagen/0/principal_' and set(image) <= {'@type', 'url', 'width', 'height'}, 'article_image_or_unknown_jsonld_media')
        need(','.join(x.name for x in body.find_all(True)) == FEATURES['body_tag_shape'], 'unknown_empty_body_structure')
        styles = body.find_all('style')
        need(len(styles) == 1 and _norm(styles[0].get_text()) == _CSS, 'unknown_body_style')
        body_copy = BeautifulSoup(str(body), 'html.parser')
        for x in body_copy(['style']):
            x.decompose()
        need(not _norm(body_copy.get_text(' ', strip=True)), 'visible_body_prose_present')
        need(not a.select('iframe,video,audio,source,embed,object,table,svg,canvas,template') and not s.select('#my-video'), 'article_media_or_unknown_embed')
        need(row.get('media_embeds') in (None, '', '[]') and row.get('media_evidence') in (None, '', '[]') and not source_check.get('independent_video_evidence'), 'native_media_evidence_present')
        # The known article images are solely empty ad banners or share icons.
        for img in a.find_all('img'):
            share = img.find_parent('ul', class_='share-buttons')
            anchor = img.find_parent('a')
            src = img.get('src', '')
            known = bool(share and src.startswith('https://static.tiempo.com.mx/assets/periodico/') and img.get('alt') in {'Facebook', 'Twitter', 'Email'})
            known |= bool(anchor and re.fullmatch(r'/hits/\d+', anchor.get('href', '')) and src.startswith('https://ads.tiempo.com.mx/uploads/banners/') and img.get('alt', '') == '')
            need(known, 'article_image_outside_known_ui')
        # Removing these independently validated channels must leave no prose.
        outside = BeautifulSoup(str(a), 'html.parser')
        for x in outside.select('header,blockquote,.complementos-container,.share-buttons'):
            x.decompose()
        need(not _norm(outside.get_text(' ', strip=True)), 'article_prose_outside_body')
        main = a.find_parent(id='main')
        need(main is not None and len(s.select('#main')) == 1 and main.name == 'div' and main.attrs == {'id':'main','class':['article']}, 'unknown_primary_article_scope')
        if main:
            rest = BeautifulSoup(str(main), 'html.parser')
            rest.select_one('article#article-post').decompose()
            for node in rest.select('a.btn-imprimir-noticia'):
                if node.get('href') == 'javascript:window.print();' and not _norm(node.get_text()):
                    node.decompose()
            rest = rest.select_one('#main')
            if _norm(rest.get_text(' ', strip=True)):
                need(recommendation_structure(rest, row) == FEATURES.get('recommendation_structure'), 'unknown_post_article_structure')
                headings = rest.find_all('h2')
                need(len(headings) == 1 and _norm(headings[0].get_text()) == 'Las Más Leídas', 'unrecognized_recommendation_heading')
                for text in rest.find_all(string=True):
                    if isinstance(text,Comment) or not _norm(text):
                        continue
                    need(text.find_parent('a') is not None or text.find_parent('h2') is not None, 'visible_prose_outside_primary_article')
            else:
                need(not rest.select('iframe,video,audio,source,object,embed,table,canvas,svg,template,img'), 'media_outside_primary_article')
        for comment in s.find_all(string=lambda x: isinstance(x, Comment)):
            need(_known_comment(str(comment), row['authors'], published, comment), 'unrecognized_comment_content')
        scripts_seen = []
        for script in s.find_all('script'):
            if script is ld[0]:
                continue
            if script.get('src'):
                need(set(script.attrs) == {'src'} and script['src'] in _EXTERNAL and not _norm(script.get_text()), 'unknown_external_script')
                scripts_seen.append(script['src'])
            else:
                key = _inline_key(script.get_text())
                need(not script.attrs and key in FEATURES['known_inline_scripts'], 'unknown_inline_script')
                scripts_seen.append(key)
        need(len(scripts_seen) == 6 and len(set(scripts_seen)) == 6, 'missing_or_duplicate_site_scripts')
        # Unknown behavior-bearing attributes cannot hide a dynamic body.
        for tag in s.find_all(True):
            for name, value in tag.attrs.items():
                if not name.startswith(('data-', 'hx-', 'on')):
                    continue
                in_share = tag.find_parent('ul', class_='share-buttons') is not None
                known = False
                if in_share and tag.name == 'a':
                    known = name in {'data-link', 'data-text'} and ('whatsapp' in tag.get('class', []))
                    if name == 'onclick':
                        known = value in {
                            "window.open('https://www.facebook.com/sharer/sharer.php?u=' + encodeURIComponent(document.URL) + '&t=' + encodeURIComponent(document.URL)); return false;",
                            "window.open('https://twitter.com/intent/tweet?text=' + encodeURIComponent(document.title) + ':%20'  + encodeURIComponent(document.URL)); return false;",
                            "window.open('mailto:?subject=' + encodeURIComponent(document.title) + '&body=' +  encodeURIComponent(document.URL)); return false;"}
                elif any(parent is a for parent in tag.parents) or tag is a:
                    known = False
                elif tag.name == 'meta':
                    known = name == 'data-page-subject' and value == 'true' and tag.get('property') in {'og:site_name','og:title','og:type','og:description','og:image'}
                elif tag.get('id') in {'weather-mobil','weather-dark','weather'}:
                    known = (name == 'hx-trigger' and value == 'load') or (name == 'hx-get' and value == {'weather-mobil':'/weather/tiempo-weatherdarkmobile/','weather-dark':'/weather/tiempo-weatherdark/','weather':'/weather/tiempo-weather/'}[tag['id']])
                elif name == 'data-toggle':
                    known = value == 'dropdown' and 'dropdown-toggle' in tag.get('class', []) or value == 'offcanvas' and 'hamburger' in tag.get('class', [])
                elif tag.get('id') == 'sticky-header':
                    known = (name,value) in {('data-spy','affix'),('data-offset-top','100')}
                elif tag.name == 'a' and 'btn-imprimir-noticia' in tag.get('class', []):
                    known = (name,value) in {('data-placement','top'),('data-original-title','Imprimir Noticia')}
                elif tag.get('id') == 'encuesta_votar':
                    known = name == 'onclick' and value == 'votar();'
                elif tag.name == 'button':
                    known = name == 'data-dismiss' and value == 'modal'
                need(known, 'unknown_dynamic_attribute')
        iframes = s.find_all('iframe')
        need(all(t.attrs == {'src':'https://www.googletagmanager.com/ns.html?id=GTM-NFMWPLG','width':'0','height':'0','style':'display:none;visibility:hidden'} and t.find_parent('noscript') is not None for t in iframes), 'unknown_document_iframe')
        need(not s.select('video,audio,source,object,embed,canvas,svg,template'), 'unknown_document_media')
        evidence.update(title_identity_verified=not any('identity' in r for r in reasons),
                        publication_evidence=published, source_body_prose_chars=len(_norm(body_copy.get_text(' ', strip=True))),
                        article_media_confirmed=False, generic_video_initializer_is_not_video=True,
                        external_scripts_executed=False, known_script_features=scripts_seen,
                        article_structure=FEATURES['article_tag_shape'])
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, OSError) as exc:
        reasons.append('classification_input_rejected:' + str(exc))
    reasons = sorted(set(reasons))
    return {'matched': not reasons, 'classification': CLASSIFICATION if not reasons else None,
            'rule_version': RULE_VERSION, 'rejection_reasons': reasons, 'evidence': evidence}
